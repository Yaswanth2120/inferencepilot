import json
from pathlib import Path

import pytest

from inferencepilot.config import SLOSpec
from inferencepilot.loadgen import AdapterBrokenError, parse_result
from inferencepilot.metrics import (
    CapacityEstimate,
    baseline_chat_capacity,
    cross_check,
    e2e_seconds,
    open_loop_loads,
    summarize,
    tpot_seconds,
)


@pytest.fixture
def raw():
    path = Path(__file__).resolve().parents[1] / "fixtures/provisional/bench_worked.json"
    return json.loads(path.read_text())


def simple_raw(count=100, failed=0, truncated=0, overlong=0, duration=10.0):
    # All transport successes have TTFT=.1 and one observed gap=.1: E2E=.2.
    # Full output is 2 tokens; truncations emit 1, overlong outputs emit 3.
    outputs = (
        [0] * failed
        + [1] * truncated
        + [3] * overlong
        + [2] * (count - failed - truncated - overlong)
    )
    completed = count - failed
    return {
        "backend": "openai",
        "num_prompts": count,
        "duration": duration,
        "completed": completed,
        "failed": failed,
        "total_input_tokens": 3 * completed,
        "total_output_tokens": sum(outputs),
        "request_throughput": completed / duration,
        "output_throughput": sum(outputs) / duration,
        "mean_ttft_ms": 100.0 if completed else 0.0,
        "p99_e2el_ms": 200.0 if completed else 0.0,
        "input_lens": [3] * count,
        "output_lens": outputs,
        "ttfts": [0.0] * failed + [0.1] * completed,
        "itls": [[] for _ in range(failed)] + [[0.1] for _ in range(completed)],
        "errors": ["failed"] * failed + [""] * completed,
    }


def test_hand_computed_distributions_rates_and_goodput(raw):
    result = summarize(parse_result(raw), 3, SLOSpec(ttft_ms=200, tpot_ms=100, e2e_ms=500))
    # TTFT [100,200,300] ms: mean/p50=200, p95=290, p99=298.
    ttft = result.distributions["ttft"]
    assert (ttft.n, ttft.mean, ttft.p50, ttft.p95, ttft.p99) == (3, 200, 200, 290, 298)
    # E2E = TTFT + sum(gaps): [.3,.5,.5] s -> p99=500ms.
    e2e = result.distributions["e2e"]
    assert e2e.n == 3 and e2e.mean == pytest.approx(1300 / 3) and e2e.p99 == 500
    # Pooled gaps [.05,.15,.3,.2] -> n=4, mean/p50=175ms, p95=285,p99=297.
    pooled = result.distributions["itl_pooled"]
    assert pooled.n == 4 and pooled.mean == 175 and pooled.p50 == 175
    assert pooled.p95 == pytest.approx(285) and pooled.p99 == 297
    # Per-request TPOT divides each sum by output_tokens-1: [100,150,100] ms.
    tpot = result.distributions["tpot_per_request"]
    assert tpot.n == 3 and tpot.mean == pytest.approx(350 / 3) and tpot.p95 == 145
    assert result.request_throughput.value == 3 / 2
    assert result.output_throughput.value == 9 / 2
    assert result.output_throughput.n == 3 and result.output_throughput.total == 9
    # Only request 1 meets all three SLOs (including TPOT equality): goodput=1/2 req/s.
    assert result.goodput.value == 0.5 and result.goodput.total == 1 and result.goodput.n == 3
    assert result.status == "ok" and result.can_compare


def test_reconstruction_does_not_trust_nonexistent_pinned_e2e_array(raw):
    raw["e2els"] = [999, 999, 999]  # Not a field emitted by pinned vLLM; ignored as extra metadata.
    result = parse_result(raw)
    assert e2e_seconds(result.requests[0]) == pytest.approx(0.3)
    assert tpot_seconds(result.requests[1]) == pytest.approx(0.15)
    assert summarize(result, 3).distributions["e2e"].p99 == 500


@pytest.mark.parametrize(
    "field", ["mean_ttft_ms", "p99_e2el_ms", "request_throughput", "output_throughput"]
)
def test_crosscheck_more_than_one_percent_is_broken(raw, field):
    raw[field] *= 1.0101
    with pytest.raises(AdapterBrokenError, match=field):
        summarize(parse_result(raw), 3)


@pytest.mark.parametrize("factor", [0.99, 1.01])
def test_crosscheck_exact_one_percent_boundary(raw, factor):
    raw["mean_ttft_ms"] *= factor
    assert summarize(parse_result(raw), 3).can_compare


@pytest.mark.parametrize("field", ["total_input_tokens", "total_output_tokens"])
def test_crosscheck_token_totals_are_exact(raw, field):
    raw[field] += 1
    with pytest.raises(AdapterBrokenError, match=field):
        cross_check(parse_result(raw))


@pytest.mark.parametrize(
    "count,failed,truncated,overlong,status",
    [
        (100, 1, 0, 0, "ok"),  # Exactly 1% is allowed by the specification.
        (100, 2, 0, 0, "partial"),  # 2% excludes the rep.
        (100, 0, 1, 0, "ok"),
        (100, 0, 2, 0, "partial"),
        (100, 0, 0, 2, "partial"),
        (10, 10, 0, 0, "failed"),
        (10, 0, 10, 0, "failed"),  # Transport success alone is insufficient for fixed-length data.
    ],
)
def test_failure_and_truncation_classification(count, failed, truncated, overlong, status):
    result = summarize(parse_result(simple_raw(count, failed, truncated, overlong)), 2)
    assert result.status == status
    assert result.failed == failed + truncated + overlong
    assert result.completed == count - result.failed
    assert (
        result.transport_failed == failed
        and result.truncated == truncated
        and result.overlong == overlong
    )
    assert result.can_compare == (status == "ok")
    assert result.distributions["ttft"].n == result.completed
    if result.failed:
        assert any("invalid requests" in note for note in result.notes)
    if status != "ok":
        assert any("excluded" in note for note in result.notes)


def test_truncated_outputs_do_not_meet_goodput_but_physical_tokens_count():
    result = summarize(
        parse_result(simple_raw(truncated=1)), 2, SLOSpec(ttft_ms=100, tpot_ms=100, e2e_ms=200)
    )
    # 99 full requests plus one short request: physical output=(99*2+1)/10=19.9 tok/s.
    # Tool request throughput remains 100/10=10; valid SLO goodput is 99/10=9.9.
    assert result.output_throughput.value == 19.9
    assert result.request_throughput.value == 10
    assert result.goodput.value == 9.9 and result.goodput.n == 100


def test_one_token_and_empty_distributions_are_not_invented_zeros(raw):
    raw.update(
        num_prompts=1,
        completed=1,
        failed=0,
        total_input_tokens=4,
        total_output_tokens=1,
        duration=1.0,
        request_throughput=1.0,
        output_throughput=1.0,
        mean_ttft_ms=100.0,
        p99_e2el_ms=100.0,
        input_lens=[4],
        output_lens=[1],
        ttfts=[0.1],
        itls=[[]],
        errors=[""],
    )
    result = summarize(parse_result(raw), 1, SLOSpec(ttft_ms=100, tpot_ms=0, e2e_ms=100))
    assert result.distributions["tpot_per_request"].n == result.distributions["itl_pooled"].n == 0
    assert result.distributions["tpot_per_request"].mean is None
    assert result.distributions["itl_pooled"].p99 is None
    assert result.goodput.value == 1  # Pinned tool defines single-token TPOT=0 only for goodput.
    failed = summarize(parse_result(simple_raw(count=2, failed=2)), 2)
    assert failed.request_throughput.value == failed.output_throughput.value == 0
    assert all(distribution.mean is None for distribution in failed.distributions.values())


def test_zero_summary_must_match_zero_recomputed_rate():
    raw = simple_raw(count=2, failed=2)
    raw["output_throughput"] = 0.0001
    with pytest.raises(AdapterBrokenError, match="output_throughput"):
        summarize(parse_result(raw), 2)


def test_measured_capacity_and_open_loop_rates():
    # At C=1, two reps give throughput 1 and 3 -> mean 2 req/s.
    # At C=8, valid reps give 3 and 5 -> mean 4 req/s; the partial rep is excluded.
    def measured(rate):
        return summarize(parse_result(simple_raw(count=2, duration=2 / rate)), 2)

    partial = summarize(parse_result(simple_raw(count=100, failed=2)), 2)
    capacity = baseline_chat_capacity(
        {1: [measured(1), measured(3)], 8: [measured(3), measured(5), partial]}
    )
    assert capacity == CapacityEstimate(4, 8, 2, 1)
    # 50%,80%,95% of measured capacity 4 -> 2,3.2,3.8; no closed-loop cap.
    loads = open_loop_loads(capacity)
    assert [load.request_rate for load in loads] == [2, 3.2, 3.8]
    assert all(load.mode == "open" and load.concurrency is None for load in loads)


def test_invalid_capacity_or_metric_inputs():
    with pytest.raises(ValueError, match="required"):
        baseline_chat_capacity({})
    with pytest.raises(ValueError, match="no comparable"):
        baseline_chat_capacity({1: []})
    with pytest.raises(ValueError, match="concurrency"):
        baseline_chat_capacity({0: []})
    for capacity in (
        CapacityEstimate(0, 1, 2, 0),
        CapacityEstimate(float("nan"), 1, 2, 0),
        CapacityEstimate(2, 1, 0, 0),
        2,
    ):
        with pytest.raises(ValueError, match="measured CapacityEstimate"):
            open_loop_loads(capacity)
    parsed = parse_result(simple_raw())
    for tokens in (0, -1, True):
        with pytest.raises(ValueError, match="positive integer"):
            summarize(parsed, tokens)


def test_zero_output_transport_success_counts_as_truncated(raw):
    # A valid HTTP stream may contain only special/empty text and tokenize to zero output.
    # It remains a tool completion, but violates any positive fixed output-length contract.
    raw.update(
        num_prompts=1,
        completed=1,
        failed=0,
        total_input_tokens=4,
        total_output_tokens=0,
        duration=1.0,
        request_throughput=1.0,
        output_throughput=0.0,
        mean_ttft_ms=100.0,
        p99_e2el_ms=100.0,
        input_lens=[4],
        output_lens=[0],
        ttfts=[0.1],
        itls=[[]],
        errors=[""],
    )
    result = summarize(parse_result(raw), 2)
    assert result.status == "failed" and result.truncated == 1 and result.transport_failed == 0
    assert result.request_throughput.value == 1 and result.output_throughput.value == 0


def test_overflowed_derived_rate_is_not_accepted_as_within_tolerance():
    raw = simple_raw(count=2)
    raw["duration"] = 1e-308  # Finite input, but 2/duration overflows the derived request rate.
    with pytest.raises(AdapterBrokenError, match="non-finite"):
        summarize(parse_result(raw), 2)
