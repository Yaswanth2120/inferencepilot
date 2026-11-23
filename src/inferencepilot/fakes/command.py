"""Fake executable implementation. Its result schema is provisional until M9."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from inferencepilot.fakes.fake_vllm import Settings, create_app, delays
from inferencepilot.vllm_flags import (
    BENCH_FLAGS,
    HELP_ALL_FLAG,
    HELP_FLAG,
    PINNED_VLLM_VERSION,
    SERVE_FLAGS,
    VERSION_FLAG,
)


def add_flags(parser, flags):
    switches = {
        "prefix_on",
        "prefix_off",
        "chunk_on",
        "chunk_off",
        "eager",
        "save_result",
        "save_detailed",
    }
    for name, flag in flags.items():
        if flag == os.environ.get("INFERENCEPILOT_FAKE_OMIT_FLAG"):
            continue
        parser.add_argument(flag, dest=name, action="store_true" if name in switches else "store")


def bench(args):
    count = int(args.num_prompts or 3)
    output_len = int(args.output_len or 4)
    input_len = int(args.input_len or 8)
    if min(count, output_len, input_len) < 1:
        raise ValueError("fake benchmark lengths and prompt count must be positive")
    schedules = [
        delays(Settings(), input_len, output_len, 1, int(args.seed or 0) + i) for i in range(count)
    ]
    ttfts = [s[0] + s[1] for s in schedules]
    itls = [s[2:] for s in schedules]
    latencies = [sum(s) for s in schedules]
    duration = sum(latencies)
    ordered = sorted(latencies)
    position = (count - 1) * 0.99
    low = int(position)
    p99 = ordered[low] + (ordered[min(low + 1, count - 1)] - ordered[low]) * (position - low)
    result = {
        "fixture_status": "provisional",
        "duration": duration,
        "completed": count,
        "total_input_tokens": count * input_len,
        "total_output_tokens": count * output_len,
        "request_throughput": count / duration,
        "output_throughput": count * output_len / duration,
        "mean_ttft_ms": sum(ttfts) / count * 1000,
        "p99_e2el_ms": p99 * 1000,
        "input_lens": [input_len] * count,
        "output_lens": [output_len] * count,
        "ttfts": ttfts,
        "itls": itls,
        "e2els": latencies,
        "errors": [""] * count,
    }
    if args.save_result:
        directory = Path(args.result_dir or ".")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (args.result_filename or "fake-bench.json")).write_text(
            json.dumps(result, indent=2) + "\n"
        )
    print(json.dumps(result))
    return 0


def serve(args):
    import uvicorn

    if os.environ.get("INFERENCEPILOT_FAKE_CRASH") == "1":
        for index in range(int(os.environ.get("INFERENCEPILOT_FAKE_CRASH_LINES", "0"))):
            print(f"startup diagnostic {index}", flush=True)
        print(
            os.environ.get(
                "INFERENCEPILOT_FAKE_CRASH_MESSAGE", "provisional: injected startup crash"
            ),
            flush=True,
        )
        return 1
    chunked_prefill = (
        not args.chunk_off or os.environ.get("INFERENCEPILOT_FAKE_FORCE_CHUNKED") == "1"
    )
    print(
        "PROVISIONAL resolved config: "
        + json.dumps(
            {
                "model": args.model,
                "max_model_len": int(args.max_model_len or 8192),
                "enable_prefix_caching": not args.prefix_off,
                "enable_chunked_prefill": chunked_prefill,
                "kv_cache_dtype": args.kv_cache_dtype or "auto",
                "max_num_batched_tokens": int(args.max_num_batched_tokens or 8192),
                "quantization": args.quantization,
                "enforce_eager": args.eager,
            }
        ),
        flush=True,
    )
    print(
        "INFO [core.py:0] Initializing a V1 LLM engine (vFAKE) with config: "
        f"model={args.model!r}, max_seq_len={int(args.max_model_len or 8192)}, "
        f"quantization={args.quantization!r}, enforce_eager={args.eager}, "
        f"enable_prefix_caching={not args.prefix_off}, "
        f"enable_chunked_prefill={chunked_prefill}",
        flush=True,
    )
    if chunked_prefill:
        print(
            "INFO [scheduler.py:0] Chunked prefill is enabled with "
            f"max_num_batched_tokens={int(args.max_num_batched_tokens or 8192)}.",
            flush=True,
        )
    print("INFO [kv_cache_utils.py:0] GPU KV cache size: 65,536 tokens", flush=True)
    print(
        "INFO [kv_cache_utils.py:0] Maximum concurrency for 8,192 tokens per request: 8.00x",
        flush=True,
    )
    print("INFO [backend.py:0] Using FAKE attention backend", flush=True)
    print(
        'INFO compilation_config={"cudagraph_mode": "NONE"}'
        if args.eager
        else 'INFO compilation_config={"cudagraph_mode": "FULL_AND_PIECEWISE"}',
        flush=True,
    )
    settings = Settings(
        model=os.environ.get("INFERENCEPILOT_FAKE_SERVED_MODEL", args.model),
        seed=int(args.seed or 0),
    )
    settings.healthy = os.environ.get("INFERENCEPILOT_FAKE_UNHEALTHY") != "1"
    for name in (
        "token_delay",
        "prefill_per_token",
        "concurrency_slowdown",
        "jitter",
        "inject_slowdown_pct",
        "failure_rate",
        "hang_rate",
        "hang_seconds",
    ):
        value = os.environ.get("INFERENCEPILOT_FAKE_" + name.upper())
        if value is not None:
            setattr(settings, name, float(value))
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(86400)"])

    def stop_child():
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

    def terminate(signum, frame):
        stop_child()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    print(f"FAKE child_pid={child.pid}", flush=True)
    try:
        if os.environ.get("INFERENCEPILOT_FAKE_NEVER_READY") == "1":
            print("FAKE startup hang", flush=True)
            time.sleep(3600)
        uvicorn.run(
            create_app(settings),
            host=args.host or "127.0.0.1",
            port=int(args.port or 8000),
            log_level="warning",
            timeout_graceful_shutdown=1,
        )
    finally:
        stop_child()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Offline fake vLLM; provisional interface")
    parser.add_argument(
        VERSION_FLAG, action="version", version=f"fake-vllm {PINNED_VLLM_VERSION} provisional"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve")
    server.add_argument("model")
    add_flags(server, SERVE_FLAGS)
    benchmark = commands.add_parser("bench")
    modes = benchmark.add_subparsers(dest="mode", required=True)
    add_flags(modes.add_parser("serve"), BENCH_FLAGS)
    args = parser.parse_args(
        [HELP_FLAG if value == HELP_ALL_FLAG else value for value in sys.argv[1:]]
    )
    return serve(args) if args.command == "serve" else bench(args)
