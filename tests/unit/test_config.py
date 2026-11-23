import pytest
from pydantic import ValidationError

from inferencepilot.config import VARIANTS, ConfigSpec, ExperimentSpec, WorkloadSpec


def test_explicit_flags():
    baseline = ConfigSpec()
    argv = baseline.argv("/fake/vllm")
    assert argv == [
        "/fake/vllm",
        "serve",
        "Qwen/Qwen3-8B",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--seed",
        "0",
        "--dtype",
        "bfloat16",
        "--max-model-len",
        "8192",
        "--gpu-memory-utilization",
        "0.9",
        "--max-num-batched-tokens",
        "8192",
        "--max-num-seqs",
        "256",
        "--kv-cache-dtype",
        "auto",
        "--enable-prefix-caching",
        "--enable-chunked-prefill",
    ]
    argv = ConfigSpec(prefix_caching=False, chunked_prefill=False, enforce_eager=True).argv()
    assert "--no-enable-prefix-caching" in argv
    assert "--no-enable-chunked-prefill" in argv
    assert "--enforce-eager" in argv


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_variant_mapping(variant):
    model, quantization = VARIANTS[variant]
    config = ConfigSpec(variant=variant, model=model, quantization=quantization)
    argv = config.argv()
    assert argv[2] == model
    if quantization:
        assert argv[argv.index("--quantization") + 1] == quantization
    else:
        assert "--quantization" not in argv


@pytest.mark.parametrize(
    "updates,message",
    [
        ({"variant": "awq"}, "requires model/quantization"),
        ({"gpu_memory_utilization": 1.1}, "less than or equal"),
        ({"gpu_memory_utilization": float("nan")}, "finite"),
        ({"max_num_batched_tokens": 32}, "must be >= max_num_seqs"),
        ({"chunked_prefill": False, "max_num_batched_tokens": 2048}, "must cover max_model_len"),
        ({"port": 0}, "greater than or equal"),
        ({"typo": 1}, "Extra inputs"),
    ],
)
def test_invalid_server_config(updates, message):
    with pytest.raises(ValidationError, match=message):
        ConfigSpec(**updates)


@pytest.mark.parametrize(
    "updates,message",
    [
        ({"concurrency": [0]}, "positive"),
        ({"concurrency": [1, 1]}, "unique"),
        ({"shared_prefix_tokens": 1}, "cannot specify"),
        ({"dataset": "prefix_repetition"}, "needs shared_prefix_tokens"),
    ],
)
def test_invalid_workload(updates, message):
    with pytest.raises(ValidationError, match=message):
        WorkloadSpec.model_validate(
            {
                "name": "chat",
                "input_tokens": 256,
                "output_tokens": 256,
                "num_prompts": 200,
                "concurrency": [1],
                **updates,
            }
        )


def test_example_validation(example):
    assert ExperimentSpec.model_validate(example).workloads[2].shared_prefix_tokens == 2048


@pytest.mark.parametrize(
    "change,message",
    [
        ("missing_calibration", "missing calibration"),
        ("duplicate_workloads", "workload names must be unique"),
        ("duplicate_levels", "nonempty and unique"),
        ("chunk_probe", "requires recorded probe evidence"),
        ("kv_probe", "requires recorded probe evidence"),
        ("length", "exceeds max_model_len"),
        ("baseline", "BF16 reference"),
        ("nonfinite", "finite"),
        ("negative", "positive"),
        ("level", "Input should be"),
        ("rep_count", "Input should be 5"),
    ],
)
def test_invalid_experiment(example, change, message):
    if change == "missing_calibration":
        example["calibration"]["rep_seconds"].pop("chat@1")
    elif change == "duplicate_workloads":
        example["workloads"].append(example["workloads"][0])
    elif change == "duplicate_levels":
        example["factors"]["max_num_seqs"] = [64, 64]
    elif change == "chunk_probe":
        example["factors"]["chunked_prefill"] = [True, False]
    elif change == "kv_probe":
        example["factors"]["kv_cache_dtype"] = ["auto", "fp8"]
    elif change == "length":
        example["workloads"][0]["input_tokens"] = 8192
    elif change == "baseline":
        example["baseline"]["prefix_caching"] = False
    elif change == "nonfinite":
        example["calibration"]["rep_seconds"]["chat@1"] = float("inf")
    elif change == "negative":
        example["calibration"]["rep_seconds"]["chat@1"] = -1
    elif change == "level":
        example["factors"]["max_num_seqs"] = [128]
    elif change == "rep_count":
        example["reps"] = 3
    with pytest.raises(ValidationError, match=message):
        ExperimentSpec.model_validate(example)
