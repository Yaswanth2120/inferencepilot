"""Fake executable implementation. Its result schema is provisional until M9."""

import argparse
import json
import math
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
        "ignore_eos",
    }
    for name, flag in flags.items():
        if flag == os.environ.get("INFERENCEPILOT_FAKE_OMIT_FLAG"):
            continue
        if name == "goodput":
            parser.add_argument(flag, dest=name, nargs="+")
        else:
            parser.add_argument(
                flag, dest=name, action="store_true" if name in switches else "store"
            )


def fake_percentile(values, percent):
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    low = int(position)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (
        position - low
    )


def bench(args):
    if os.environ.get("INFERENCEPILOT_FAKE_BENCH_CRASH") == "1":
        print("injected benchmark failure", file=sys.stderr)
        return 1
    count = int(args.num_prompts or 3)
    prefix = args.dataset == "prefix_repetition"
    output_len = int((args.prefix_output_len if prefix else args.output_len) or 4)
    input_len = (
        (int(args.prefix_len or 0) + int(args.suffix_len or 8))
        if prefix
        else int(args.input_len or 8)
    )
    concurrency = int(args.concurrency or 1)
    if min(count, output_len, input_len, concurrency) < 1:
        raise ValueError("fake benchmark counts and lengths must be positive")
    settings = Settings(
        inject_slowdown_pct=float(os.environ.get("INFERENCEPILOT_FAKE_INJECT_SLOWDOWN_PCT", "0"))
    )
    fail_every = int(os.environ.get("INFERENCEPILOT_FAKE_BENCH_FAIL_EVERY", "0"))
    truncate_every = int(os.environ.get("INFERENCEPILOT_FAKE_BENCH_TRUNCATE_EVERY", "0"))
    outputs, ttfts, itls, errors, elapsed = [], [], [], [], []
    for index in range(count):
        failed = fail_every > 0 and (index + 1) % fail_every == 0
        tokens = output_len - int(truncate_every > 0 and (index + 1) % truncate_every == 0)
        schedule = delays(
            settings, input_len, max(1, tokens), concurrency, int(args.seed or 0) + index
        )
        elapsed.append(sum(schedule))
        outputs.append(0 if failed else tokens)
        ttfts.append(0 if failed else schedule[0] + schedule[1])
        itls.append([] if failed else schedule[2:])
        errors.append("injected request failure" if failed else "")
    rate = float(args.request_rate or "inf")
    starts = []
    available = [0.0] * min(concurrency, count)
    for index, latency in enumerate(elapsed):
        lane = index % len(available)
        start = index / rate if math.isfinite(rate) else available[lane]
        starts.append(start)
        available[lane] = start + latency
    duration = max(start + latency for start, latency in zip(starts, elapsed))
    successful = [i for i in range(count) if not errors[i]]
    latencies = [ttfts[i] + sum(itls[i]) for i in successful]
    completed_ttfts = [ttfts[i] for i in successful]
    result = {
        "fixture_status": "provisional",
        "backend": args.backend or "openai",
        "num_prompts": count,
        "duration": duration,
        "completed": len(successful),
        "failed": count - len(successful),
        "total_input_tokens": len(successful) * input_len,
        "total_output_tokens": sum(outputs),
        "request_throughput": len(successful) / duration,
        "output_throughput": sum(outputs) / duration,
        "mean_ttft_ms": sum(completed_ttfts) / len(successful) * 1000 if successful else 0,
        "p99_e2el_ms": fake_percentile(latencies, 99) * 1000,
        "input_lens": [input_len] * count,
        "output_lens": outputs,
        "ttfts": ttfts,
        "itls": itls,
        "errors": errors,
        "start_times": starts,
        "generated_texts": [
            "synthetic completion" if i in successful else "" for i in range(count)
        ],
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
