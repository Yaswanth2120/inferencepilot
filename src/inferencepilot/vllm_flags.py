"""Versioned CLI vocabulary and declarative ConfigSpec mapping; no logic."""

PINNED_VLLM_VERSION = "0.15.1"
HELP_FLAG = "--help"
HELP_ALL_FLAG = "--help=all"
VERSION_FLAG = "--version"

SERVE_FLAGS = {
    "host": "--host",
    "port": "--port",
    "seed": "--seed",
    "dtype": "--dtype",
    "quantization": "--quantization",
    "max_model_len": "--max-model-len",
    "gpu_memory_utilization": "--gpu-memory-utilization",
    "max_num_batched_tokens": "--max-num-batched-tokens",
    "max_num_seqs": "--max-num-seqs",
    "kv_cache_dtype": "--kv-cache-dtype",
    "prefix_on": "--enable-prefix-caching",
    "prefix_off": "--no-enable-prefix-caching",
    "chunk_on": "--enable-chunked-prefill",
    "chunk_off": "--no-enable-chunked-prefill",
    "eager": "--enforce-eager",
}
BENCH_FLAGS = {
    "backend": "--backend",
    "host": "--host",
    "port": "--port",
    "endpoint": "--endpoint",
    "dataset": "--dataset-name",
    "model": "--model",
    "seed": "--seed",
    "num_prompts": "--num-prompts",
    "input_len": "--random-input-len",
    "output_len": "--random-output-len",
    "result_dir": "--result-dir",
    "result_filename": "--result-filename",
    "save_result": "--save-result",
    "save_detailed": "--save-detailed",
    "range_ratio": "--random-range-ratio",
    "prefix_len": "--prefix-repetition-prefix-len",
    "suffix_len": "--prefix-repetition-suffix-len",
    "num_prefixes": "--prefix-repetition-num-prefixes",
    "prefix_output_len": "--prefix-repetition-output-len",
    "warmups": "--num-warmups",
    "ignore_eos": "--ignore-eos",
    "temperature": "--temperature",
    "request_rate": "--request-rate",
    "concurrency": "--max-concurrency",
    "burstiness": "--burstiness",
    "percentile_metrics": "--percentile-metrics",
    "percentiles": "--metric-percentiles",
    "goodput": "--goodput",
}
CONFIG_FLAGS = {
    "host": SERVE_FLAGS["host"],
    "port": SERVE_FLAGS["port"],
    "seed": SERVE_FLAGS["seed"],
    "dtype": SERVE_FLAGS["dtype"],
    "quantization": SERVE_FLAGS["quantization"],
    "max_model_len": SERVE_FLAGS["max_model_len"],
    "gpu_memory_utilization": SERVE_FLAGS["gpu_memory_utilization"],
    "max_num_batched_tokens": SERVE_FLAGS["max_num_batched_tokens"],
    "max_num_seqs": SERVE_FLAGS["max_num_seqs"],
    "kv_cache_dtype": SERVE_FLAGS["kv_cache_dtype"],
}
USED_FLAGS = {"serve": tuple(SERVE_FLAGS.values()), "bench serve": tuple(BENCH_FLAGS.values())}
