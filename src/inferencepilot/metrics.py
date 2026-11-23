"""Derive request metrics and verify the vLLM adapter; no process or filesystem I/O."""

import math
from dataclasses import dataclass

from inferencepilot import stats
from inferencepilot.config import LoadSpec, SLOSpec
from inferencepilot.loadgen import AdapterBrokenError


@dataclass(frozen=True)
class Distribution:
    n: int
    mean: float | None
    p50: float | None
    p95: float | None
    p99: float | None
    unit: str = "ms"


@dataclass(frozen=True)
class Rate:
    value: float
    n: int
    total: int
    duration_s: float
    unit: str


@dataclass(frozen=True)
class RepMetrics:
    status: str
    attempted: int
    completed: int
    failed: int
    transport_failed: int
    truncated: int
    overlong: int
    distributions: dict[str, Distribution]
    request_throughput: Rate
    output_throughput: Rate
    goodput: Rate | None
    notes: tuple[str, ...]

    @property
    def can_compare(self):
        return self.status == "ok"


@dataclass(frozen=True)
class CapacityEstimate:
    requests_per_second: float
    concurrency: int
    n_reps: int
    excluded_reps: int


def e2e_seconds(request):
    """Reconstruct E2E from the pinned completion backend's available timing arrays."""
    return request.ttft_s + math.fsum(request.gaps_s)


def tpot_seconds(request):
    """Return token-average decode time; one/zero-token outputs have no defined TPOT."""
    if request.output_tokens <= 1:
        return None
    return math.fsum(request.gaps_s) / (request.output_tokens - 1)


def distribution(values_s):
    """Summarize seconds in milliseconds with observation count and no invented empty values."""
    values = [value * 1000 for value in values_s]
    if not values:
        return Distribution(0, None, None, None, None)
    return Distribution(
        len(values),
        stats.mean(values),
        stats.percentile(values, 50),
        stats.percentile(values, 95),
        stats.percentile(values, 99),
    )


def cross_check(result):
    """Fail on incompatible token totals or more than 1% summary disagreement."""
    successful = [request for request in result.requests if request.success]
    expected = {
        "mean_ttft_ms": stats.mean(request.ttft_s for request in successful) * 1000
        if successful
        else 0,
        "p99_e2el_ms": stats.percentile([e2e_seconds(request) for request in successful], 99) * 1000
        if successful
        else 0,
        "request_throughput": len(successful) / result.duration_s,
        "output_throughput": sum(request.output_tokens for request in successful)
        / result.duration_s,
    }
    for field, recomputed in expected.items():
        if not math.isfinite(recomputed):
            raise AdapterBrokenError(f"adapter broken: {field} recomputed a non-finite value")
        reported = result.tool_summary[field]
        difference = abs(reported - recomputed)
        limit = abs(recomputed) * 0.01
        if difference > limit and not math.isclose(difference, limit, rel_tol=1e-12, abs_tol=0):
            raise AdapterBrokenError(
                f"adapter broken: {field} reported={reported}, recomputed={recomputed}"
            )
    totals = {
        "total_input_tokens": sum(request.input_tokens for request in successful),
        "total_output_tokens": sum(request.output_tokens for request in successful),
    }
    for field, recomputed in totals.items():
        if result.tool_summary[field] != recomputed:
            raise AdapterBrokenError(f"adapter broken: {field} disagrees with detailed arrays")


def summarize(result, expected_output_tokens, slo=None):
    """Verify the adapter, classify the rep, and derive latency/throughput/goodput views."""
    if (
        isinstance(expected_output_tokens, bool)
        or not isinstance(expected_output_tokens, int)
        or expected_output_tokens <= 0
    ):
        raise ValueError("expected_output_tokens must be a positive integer")
    if slo is not None:
        slo = SLOSpec.model_validate(slo.model_dump())
    cross_check(result)
    successful = [request for request in result.requests if request.success]
    valid = [request for request in successful if request.output_tokens == expected_output_tokens]
    attempted = len(result.requests)
    transport_failed = attempted - len(successful)
    truncated = sum(request.output_tokens < expected_output_tokens for request in successful)
    overlong = sum(request.output_tokens > expected_output_tokens for request in successful)
    failed = transport_failed + truncated + overlong
    status = "failed" if not valid else "partial" if failed * 100 > attempted else "ok"
    distributions = {
        "ttft": distribution(request.ttft_s for request in valid),
        "e2e": distribution(e2e_seconds(request) for request in valid),
        "itl_pooled": distribution(gap for request in valid for gap in request.gaps_s),
        "tpot_per_request": distribution(
            tpot_seconds(request) for request in valid if request.output_tokens > 1
        ),
    }
    token_total = sum(request.output_tokens for request in successful)
    request_rate = Rate(
        len(successful) / result.duration_s,
        attempted,
        len(successful),
        result.duration_s,
        "requests/s",
    )
    output_rate = Rate(
        token_total / result.duration_s, attempted, token_total, result.duration_s, "tokens/s"
    )
    goodput = None
    if slo is not None:
        good = sum(
            request.ttft_s * 1000 <= slo.ttft_ms
            and (tpot_seconds(request) or 0) * 1000 <= slo.tpot_ms
            and e2e_seconds(request) * 1000 <= slo.e2e_ms
            for request in valid
        )
        goodput = Rate(good / result.duration_s, attempted, good, result.duration_s, "requests/s")
    notes = [
        "E2E reconstructed from TTFT plus observed streaming gaps; parser is provisional.",
        "Pooled ITL describes streaming gaps; a gap may span multiple output tokens.",
        "Latency distributions exclude failed and non-fixed-length requests; physical "
        "throughput includes tokens from all transport-successful requests.",
    ]
    if failed:
        notes.append(
            f"{failed}/{attempted} invalid requests: {transport_failed} transport failures, "
            f"{truncated} truncated, {overlong} overlong."
        )
    if status != "ok":
        notes.append("Rep excluded from comparisons: no valid requests or more than 1% failures.")
    return RepMetrics(
        status,
        attempted,
        len(valid),
        failed,
        transport_failed,
        truncated,
        overlong,
        distributions,
        request_rate,
        output_rate,
        goodput,
        tuple(notes),
    )


def baseline_chat_capacity(points):
    """Take the maximum comparable mean rate over supplied baseline chat closed-loop points."""
    if not points:
        raise ValueError("measured baseline chat closed-loop points are required")
    estimates = []
    excluded = 0
    for concurrency, reps in points.items():
        if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency <= 0:
            raise ValueError("capacity point concurrency must be positive")
        valid = [rep for rep in reps if rep.can_compare]
        excluded += len(reps) - len(valid)
        if valid:
            rate = stats.mean(rep.request_throughput.value for rep in valid)
            estimates.append((rate, concurrency, len(valid)))
    if not estimates:
        raise ValueError("no comparable baseline capacity reps")
    rate, concurrency, n_reps = max(estimates, key=lambda estimate: (estimate[0], -estimate[1]))
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("measured baseline capacity must be finite and positive")
    return CapacityEstimate(rate, concurrency, n_reps, excluded)


def open_loop_loads(capacity):
    """Return uncapped Poisson-rate specifications at 50%, 80%, and 95% of capacity."""
    if (
        not isinstance(capacity, CapacityEstimate)
        or capacity.n_reps < 1
        or not math.isfinite(capacity.requests_per_second)
        or capacity.requests_per_second <= 0
    ):
        raise ValueError("a positive measured CapacityEstimate with its rep count is required")
    return tuple(
        LoadSpec(mode="open", request_rate=capacity.requests_per_second * fraction)
        for fraction in (0.50, 0.80, 0.95)
    )
