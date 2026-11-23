"""Validated, serializable experiment data; no filesystem or process access."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from inferencepilot.vllm_flags import CONFIG_FLAGS, PINNED_VLLM_VERSION, SERVE_FLAGS

VARIANTS = {
    "bf16": ("Qwen/Qwen3-8B", None),
    "fp8_online": ("Qwen/Qwen3-8B", "fp8"),
    "awq": ("Qwen/Qwen3-8B-AWQ", "awq"),
    "fp8_ckpt": ("Qwen/Qwen3-8B-FP8", "fp8"),
}
Variant = Literal["bf16", "fp8_online", "awq", "fp8_ckpt"]


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class ConfigSpec(Spec):
    variant: Variant = "bf16"
    model: str = "Qwen/Qwen3-8B"
    quantization: Literal["fp8", "awq"] | None = None
    dtype: Literal["bfloat16"] = "bfloat16"
    gpu_memory_utilization: float = Field(default=0.90, gt=0, le=1)
    max_model_len: int = Field(default=8192, gt=0)
    max_num_batched_tokens: int = Field(default=8192, gt=0)
    max_num_seqs: int = Field(default=256, gt=0)
    prefix_caching: bool = True
    chunked_prefill: bool = True
    kv_cache_dtype: Literal["auto", "fp8"] = "auto"
    enforce_eager: bool = False
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def valid_combination(self):
        if (self.model, self.quantization) != VARIANTS[self.variant]:
            raise ValueError(f"{self.variant} requires model/quantization {VARIANTS[self.variant]}")
        if self.max_num_batched_tokens < self.max_num_seqs:
            raise ValueError("max_num_batched_tokens must be >= max_num_seqs")
        if not self.chunked_prefill and self.max_num_batched_tokens < self.max_model_len:
            raise ValueError("without chunked prefill, token budget must cover max_model_len")
        return self

    def argv(self, binary="vllm"):
        args = [binary, "serve", self.model]
        for field, flag in CONFIG_FLAGS.items():
            value = getattr(self, field)
            if value is not None:
                args.extend([flag, str(value)])
        args.append(SERVE_FLAGS["prefix_on" if self.prefix_caching else "prefix_off"])
        args.append(SERVE_FLAGS["chunk_on" if self.chunked_prefill else "chunk_off"])
        if self.enforce_eager:
            args.append(SERVE_FLAGS["eager"])
        return args


class WorkloadSpec(Spec):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    dataset: Literal["random", "prefix_repetition"] = "random"
    input_tokens: int = Field(gt=0)
    output_tokens: int = Field(gt=0)
    shared_prefix_tokens: int = Field(default=0, ge=0)
    concurrency: list[int] = Field(min_length=1)
    num_prompts: int = Field(gt=0)
    warmups: int = Field(default=10, ge=0)
    ignore_eos: Literal[True] = True

    @model_validator(mode="after")
    def valid_workload(self):
        if any(value <= 0 for value in self.concurrency):
            raise ValueError("concurrency levels must be positive")
        if len(set(self.concurrency)) != len(self.concurrency):
            raise ValueError("concurrency levels must be unique")
        if self.dataset == "prefix_repetition" and self.shared_prefix_tokens == 0:
            raise ValueError("prefix_repetition needs shared_prefix_tokens > 0")
        if self.dataset == "random" and self.shared_prefix_tokens:
            raise ValueError("random workload cannot specify a shared prefix")
        return self


class Factors(Spec):
    variants: list[Variant] = Field(default_factory=lambda: list(VARIANTS))
    prefix_caching: list[bool] = Field(default_factory=lambda: [True, False])
    max_num_batched_tokens: list[Literal[2048, 8192, 16384]] = Field(
        default_factory=lambda: [2048, 8192, 16384]
    )
    max_num_seqs: list[Literal[64, 256]] = Field(default_factory=lambda: [64, 256])
    chunked_prefill: list[bool] = Field(default_factory=lambda: [True])
    kv_cache_dtype: list[Literal["auto", "fp8"]] = Field(default_factory=lambda: ["auto"])

    @model_validator(mode="after")
    def unique_levels(self):
        for name in type(self).model_fields:
            values = getattr(self, name)
            if not values or len(values) != len(set(values)):
                raise ValueError(f"{name} levels must be nonempty and unique")
        return self


class ProbeEvidence(Spec):
    status: Literal["supported", "unsupported_on_hardware"]
    evidence: str = Field(min_length=1)


class Calibration(Spec):
    source: Literal["synthetic", "measured"]
    note: str = Field(min_length=1)
    startup_seconds: float = Field(ge=0)
    teardown_seconds: float = Field(ge=0)
    rep_seconds: dict[str, float]
    extra_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def positive_reps(self):
        if any(value <= 0 for value in self.rep_seconds.values()):
            raise ValueError("calibration rep durations must be positive")
        return self


class ExperimentSpec(Spec):
    name: str = Field(min_length=1)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)
    vllm_version: Literal[PINNED_VLLM_VERSION] = PINNED_VLLM_VERSION
    baseline: ConfigSpec = Field(default_factory=ConfigSpec)
    factors: Factors = Field(default_factory=Factors)
    workloads: list[WorkloadSpec] = Field(min_length=1)
    calibration: Calibration
    reps: Literal[5] = 5
    max_gpu_hours: float = Field(default=14, gt=0)
    probes: dict[str, ProbeEvidence] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_experiment(self):
        baseline = self.baseline
        required = ConfigSpec(port=baseline.port, seed=baseline.seed)
        if baseline != required:
            raise ValueError("baseline must use the section 5.2 BF16 reference settings")
        names = [workload.name for workload in self.workloads]
        if len(names) != len(set(names)):
            raise ValueError("workload names must be unique")
        for workload in self.workloads:
            length = workload.input_tokens + workload.shared_prefix_tokens + workload.output_tokens
            if length > baseline.max_model_len:
                raise ValueError(f"{workload.name} exceeds max_model_len")
            for concurrency in workload.concurrency:
                key = f"{workload.name}@{concurrency}"
                if key not in self.calibration.rep_seconds:
                    raise ValueError(f"missing calibration duration for {key}")
        for key, optional in (
            ("chunked_prefill_off", False in self.factors.chunked_prefill),
            ("kv_cache_fp8", "fp8" in self.factors.kv_cache_dtype),
        ):
            if optional and key not in self.probes:
                raise ValueError(f"{key} requires recorded probe evidence before inclusion")
        unknown = set(self.probes) - (set(VARIANTS) | {"chunked_prefill_off", "kv_cache_fp8"})
        if unknown:
            raise ValueError(f"unknown probe keys: {sorted(unknown)}")
        return self


class PlannedConfig(Spec):
    label: str
    role: Literal["baseline", "candidate", "combined", "seeded_regression"]
    spec: ConfigSpec | None
    probe_status: Literal["supported", "pending", "unsupported_on_hardware", "pending_selection"]
    note: str = ""


class PointSpec(Spec):
    workload: str
    mode: Literal["closed"] = "closed"
    concurrency: int = Field(gt=0)
    num_prompts: int = Field(gt=0)
    warmups: int = Field(ge=0)
    rep_seeds: list[int]
    estimated_seconds: float = Field(ge=0)


class LaunchSpec(Spec):
    config_label: str
    ordinal: int = Field(ge=1)
    points: list[PointSpec]
    estimated_seconds: float = Field(ge=0)


class ExperimentPlan(Spec):
    schema_version: Literal[1] = 1
    experiment: ExperimentSpec
    configs: list[PlannedConfig]
    launches: list[LaunchSpec]
    estimated_gpu_hours: float = Field(ge=0)
    budget_exceeded: bool
    warnings: list[str]


class LoadSpec(Spec):
    mode: Literal["closed", "open"] = "closed"
    concurrency: int | None = Field(default=None, gt=0, strict=True)
    request_rate: float | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def valid_load(self):
        if self.mode == "closed" and (self.concurrency is None or self.request_rate is not None):
            raise ValueError("closed load needs concurrency and no request_rate")
        if self.mode == "open" and (self.request_rate is None or self.concurrency is not None):
            raise ValueError("open load needs request_rate and no concurrency cap")
        return self


class SLOSpec(Spec):
    ttft_ms: float = Field(ge=0, strict=True)
    tpot_ms: float = Field(ge=0, strict=True)
    e2e_ms: float = Field(ge=0, strict=True)
