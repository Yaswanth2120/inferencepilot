"""vLLM benchmark argument construction and provisional detailed-result parsing."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from inferencepilot.config import BenchmarkEndpoint, ConfigSpec, LoadSpec, SLOSpec, WorkloadSpec
from inferencepilot.vllm_flags import BENCH_FLAGS

NonnegativeFloat = Annotated[float, Field(ge=0)]
NonnegativeInt = Annotated[int, Field(ge=0)]


class AdapterBrokenError(ValueError):
    """Raw result structure or recomputed summaries violate the adapter contract."""


class DetailedResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)
    backend: Literal["openai"]
    num_prompts: int = Field(gt=0)
    duration: float = Field(gt=0)
    completed: NonnegativeInt
    failed: NonnegativeInt
    total_input_tokens: NonnegativeInt
    total_output_tokens: NonnegativeInt
    request_throughput: NonnegativeFloat
    output_throughput: NonnegativeFloat
    mean_ttft_ms: NonnegativeFloat
    p99_e2el_ms: NonnegativeFloat
    input_lens: list[NonnegativeInt]
    output_lens: list[NonnegativeInt]
    ttfts: list[NonnegativeFloat]
    itls: list[list[NonnegativeFloat]]
    errors: list[str]

    @model_validator(mode="after")
    def aligned_requests(self):
        for field in ("input_lens", "output_lens", "ttfts", "itls", "errors"):
            if len(getattr(self, field)) != self.num_prompts:
                raise ValueError(f"{field} must align with num_prompts; detailed arrays required")
        observed = sum(not error for error in self.errors)
        if self.completed != observed or self.completed + self.failed != self.num_prompts:
            raise ValueError("completed/failed counts disagree with per-request outcomes")
        if any(error and tokens for error, tokens in zip(self.errors, self.output_lens)):
            raise ValueError("failed request output_lens must be zero in the pinned schema")
        return self


@dataclass(frozen=True)
class RequestResult:
    input_tokens: int
    output_tokens: int
    ttft_s: float
    gaps_s: tuple[float, ...]
    error: str

    @property
    def success(self):
        return not self.error


@dataclass(frozen=True)
class BenchmarkResult:
    duration_s: float
    requests: tuple[RequestResult, ...]
    tool_summary: dict
    parser_status: str = "provisional"


def build_command(config, workload, load, seed, result_path, binary="vllm", slo=None):
    """Build fixed-length streaming benchmark argv without running or writing anything."""
    config = (
        BenchmarkEndpoint if isinstance(config, BenchmarkEndpoint) else ConfigSpec
    ).model_validate(config.model_dump())
    workload = WorkloadSpec.model_validate(workload.model_dump())
    load = LoadSpec.model_validate(load.model_dump())
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("benchmark seed must be an integer in [0, 2^32-1]")
    if (
        workload.input_tokens + workload.shared_prefix_tokens + workload.output_tokens
        > config.max_model_len
    ):
        raise ValueError("workload exceeds the server max_model_len")
    if load.mode == "closed" and load.concurrency not in workload.concurrency:
        raise ValueError("closed concurrency is not a configured workload point")
    path = Path(result_path)
    if path.suffix != ".json":
        raise ValueError("benchmark result_path must name a JSON file")
    args = [str(binary), "bench", "serve"]
    values = {
        "backend": "openai",
        "host": config.host,
        "port": config.port,
        "endpoint": "/v1/completions",
        "model": config.model,
        "dataset": workload.dataset,
        "seed": seed,
        "num_prompts": workload.num_prompts,
        "warmups": workload.warmups,
        "temperature": 0,
        "request_rate": "inf" if load.mode == "closed" else load.request_rate,
        "burstiness": 1.0,
        "percentile_metrics": "ttft,tpot,itl,e2el",
        "percentiles": "50,95,99",
        "result_dir": str(path.parent),
        "result_filename": path.name,
    }
    if load.mode == "closed":
        values["concurrency"] = load.concurrency
    if workload.dataset == "random":
        values.update(
            input_len=workload.input_tokens, output_len=workload.output_tokens, range_ratio=0
        )
    else:
        values.update(
            prefix_len=workload.shared_prefix_tokens,
            suffix_len=workload.input_tokens,
            num_prefixes=1,
            prefix_output_len=workload.output_tokens,
        )
    for key, value in values.items():
        args.extend([BENCH_FLAGS[key], str(value)])
    args.extend(
        [BENCH_FLAGS["ignore_eos"], BENCH_FLAGS["save_result"], BENCH_FLAGS["save_detailed"]]
    )
    if slo is not None:
        slo = SLOSpec.model_validate(slo.model_dump())
        args.extend(
            [
                BENCH_FLAGS["goodput"],
                f"ttft:{slo.ttft_ms}",
                f"tpot:{slo.tpot_ms}",
                f"e2el:{slo.e2e_ms}",
            ]
        )
    return args


def parse_result(data):
    """Validate consumed fields of pinned generation JSON and preserve per-request raw values."""
    try:
        raw = DetailedResult.model_validate(data)
    except ValidationError as error:
        raise AdapterBrokenError(f"adapter broken: invalid detailed result: {error}") from error
    requests = tuple(
        RequestResult(inputs, outputs, ttft, tuple(gaps), error)
        for inputs, outputs, ttft, gaps, error in zip(
            raw.input_lens, raw.output_lens, raw.ttfts, raw.itls, raw.errors
        )
    )
    fields = (
        "completed",
        "failed",
        "total_input_tokens",
        "total_output_tokens",
        "request_throughput",
        "output_throughput",
        "mean_ttft_ms",
        "p99_e2el_ms",
    )
    return BenchmarkResult(raw.duration, requests, {field: getattr(raw, field) for field in fields})
