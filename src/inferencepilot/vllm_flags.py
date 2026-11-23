"""Provisional CLI vocabulary shared by the fake and future adapters; no logic."""

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
    "model": "--model",
    "seed": "--seed",
    "num_prompts": "--num-prompts",
    "input_len": "--random-input-len",
    "output_len": "--random-output-len",
    "result_dir": "--result-dir",
    "result_filename": "--result-filename",
    "save_result": "--save-result",
    "save_detailed": "--save-detailed",
}
# No production adapter exists in M0. M1 populates this from its actual command builders.
USED_FLAGS = {}
