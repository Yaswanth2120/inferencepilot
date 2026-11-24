#!/usr/bin/env python3
"""Benchmark an explicitly selected existing server without starting/stopping it."""

import argparse
import fcntl
import json
import random
import signal
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from inferencepilot import analysis, env
from inferencepilot.config import BenchmarkEndpoint, LoadSpec, WorkloadSpec
from inferencepilot.loadgen import build_command, parse_result
from inferencepilot.metrics import summarize
from inferencepilot.runner import execute
from inferencepilot.store import Store, encode
from inferencepilot.vllm_flags import HELP_ALL_FLAG


def endpoint(client, model):
    """Verify the served model identity and its actual advertised context limit."""
    response = client.get("/v1/models")
    response.raise_for_status()
    matches = [entry for entry in response.json()["data"] if entry["id"] == model]
    if len(matches) != 1 or not matches[0].get("max_model_len"):
        raise ValueError("expected exactly one matching model with an advertised context limit")
    return matches[0]


def telemetry():
    """Capture read-only GPU clocks, power, thermal and memory state around each rep."""
    return env.command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,clocks.sm,clocks.mem,power.draw,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )


def progress(store, identity, phase, error=None):
    """Persist a small reconnectable status file next to the campaign database."""
    records = store.records(identity)
    data = dict(
        experiment=identity,
        phase=phase,
        updated_at=time.time(),
        reps=len(records["reps"]),
        ok_reps=sum(r["status"] == "ok" for r in records["reps"]),
        error=error,
        billing="This benchmark does not stop the existing server or rental billing.",
    )
    temporary = store.path.parent / "status.tmp"
    temporary.write_text(encode(data))
    temporary.replace(store.path.parent / "status.json")


def render(store, identity):
    """Report shared rep-level statistics with explicit single-lifetime inference limits."""
    records = store.records(identity)
    rows = analysis.aggregate(records)
    bundle = dict(
        experiment=records["experiment"],
        configs=records["configs"],
        launches=records["launches"],
        metrics=rows,
        reps=records["reps"],
        environment=json.loads(
            store.rows("env_snapshots", id=records["experiment"]["env_id"])[0]["data"]
        ),
        limits=[
            "Existing server observed, never restarted; one server lifetime, no between-launch MDE or config-regression claims.",
            "Raw-completion synthetic performance only; no chat-template, reasoning-quality or GSM8K claims.",
            "Only the advertised context limit is verified. Higher context limits, OOM boundary and startup time: not run (needs GPU restart).",
            "User explicitly selected the preinstalled GPT-OSS model and vLLM version instead of the gated Qwen/pinned-version campaign.",
        ],
    )
    directory = store.path.parent / "reports"
    directory.mkdir(exist_ok=True)
    (directory / "report.json").write_text(encode(bundle) + "\n")
    lines = [
        "# GPT-OSS existing-server performance validation",
        "",
        records["experiment"]["status"],
        "",
        *bundle["limits"],
        "",
        "| Point | Metric | Mean | 95% CI | n reps |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['point']} | {row['metric']} | {row['mean']:.6g} | [{row['ci_low']:.6g}, {row['ci_high']:.6g}] | {row['n_reps']} |"
        )
    invalid = [
        dict(id=r["id"], status=r["status"], summary=json.loads(r["summary"]))
        for r in records["reps"]
        if r["status"] != "ok"
    ]
    lines.extend(
        [
            "",
            "Excluded reps: `" + encode(invalid) + "`",
            "",
            "## Observed configuration",
            "",
            "```json",
            json.dumps([json.loads(c["spec"]) for c in records["configs"]], indent=2),
            "```",
            "",
            "## Environment",
            "",
            "```json",
            json.dumps(bundle["environment"], indent=2),
            "```",
            "",
        ]
    )
    (directory / "report.md").write_text("\n".join(lines))


def interrupt(signum, frame):
    raise KeyboardInterrupt


def run(args):
    """Checkpoint five reps per point against an external server under a fixed deadline."""
    store = Store(args.db)
    client = httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=30, trust_env=False)
    model = endpoint(client, args.model)
    target = BenchmarkEndpoint(
        model=args.model, port=args.port, max_model_len=model["max_model_len"]
    )
    help_output = env.command_output([args.binary, "bench", "serve", HELP_ALL_FLAG])
    if not help_output["available"]:
        raise ValueError("benchmark help unavailable")
    help_text = help_output["output"]
    workloads = [
        WorkloadSpec(
            name=name,
            dataset="random",
            input_tokens=tokens,
            output_tokens=256,
            concurrency=[1, 8, 32],
            num_prompts=args.prompts,
            warmups=10,
        )
        for name, tokens in [("chat", 256), ("rag", 4096)]
    ]
    seeds = [random.Random(42 + rep).randrange(2**32) for rep in range(5)]
    plan = dict(
        kind="existing-server",
        target=target.model_dump(),
        workloads=[w.model_dump() for w in workloads],
        seeds=seeds,
        hours=args.hours,
    )
    if args.resume:
        identity = args.resume
        row = store.rows("experiments", id=identity)[0]
        if json.loads(row["plan"]) != plan:
            raise ValueError("resume options differ from saved experiment")
        created = row["created_at"]
        launch = store.records(identity)["launches"][0]["id"]
    else:
        created = time.time()
        env_id = store.insert("env_snapshots", created_at=created, data=encode(env.snapshot()))
        identity = store.insert(
            "experiments",
            name="GPT-OSS-120B existing-server validation",
            created_at=created,
            plan=encode(plan),
            status="running",
            env_id=env_id,
            budget_gpu_hours=args.hours,
            seed=42,
        )
        config_id = store.insert(
            "configs",
            experiment_id=identity,
            label="existing-gptoss",
            role="baseline",
            spec=encode(
                {
                    **target.model_dump(),
                    "observed_model": model,
                    "ownership": "external",
                    "context_limit_source": "/v1/models; not an OOM search",
                }
            ),
            spec_hash=__import__("hashlib")
            .sha256(encode(target.model_dump()).encode())
            .hexdigest(),
        )
        launch = store.insert(
            "launches",
            config_id=config_id,
            ordinal=1,
            started_at=created,
            status="ok",
            cmd="[]",
            resolved_args=encode(
                {
                    "ownership": "external",
                    "observed_at": created,
                    "actual_start_time": None,
                    "note": "started_at is observation time, not server startup",
                    "model": model,
                }
            ),
            log_path=args.startup_log,
        )
    deadline = created + args.hours * 3600
    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        store.update("experiments", identity, status="running", abort_reason=None)
        progress(store, identity, "running")
        for concurrency in (1, 8, 32):
            for workload in workloads:
                endpoint(client, args.model)
                point = store.insert(
                    "points",
                    launch_id=launch,
                    workload=workload.name,
                    mode="closed",
                    concurrency=concurrency,
                    num_prompts=workload.num_prompts,
                    params=encode({"seeds": seeds, "external_server": True}),
                )
                for rep, seed in enumerate(seeds):
                    key = f"external:{identity}:{workload.name}:{concurrency}:{rep}"
                    if store.meta(key):
                        continue
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise TimeoutError("existing-server benchmark budget exhausted")
                    raw = store.artifact(f"{point}-{rep}.json")
                    command = build_command(
                        target,
                        workload,
                        LoadSpec(concurrency=concurrency),
                        seed,
                        raw,
                        binary=args.binary,
                    )
                    missing = [
                        arg for arg in command if arg.startswith("--") and arg not in help_text
                    ]
                    if missing:
                        raise ValueError(f"installed benchmark lacks flags: {missing}")
                    started, before = time.time(), telemetry()
                    execute(command, raw.with_suffix(".log"), min(remaining, 1800))
                    parsed = parse_result(json.loads(raw.read_text()))
                    summary = summarize(parsed, workload.output_tokens)
                    store.checkpoint_rep(
                        key,
                        point_id=point,
                        rep=rep,
                        seed=seed,
                        started_at=started,
                        duration_s=parsed.duration_s,
                        status=summary.status,
                        completed=summary.completed,
                        failed=summary.failed,
                        raw_path=str(raw),
                        summary=encode(asdict(summary)),
                        tool_summary=encode(parsed.tool_summary),
                        gpu_before=encode(before),
                        gpu_after=encode(telemetry()),
                    )
                    progress(store, identity, "running")
                    print(
                        f"{workload.name}@{concurrency} rep {rep + 1}/5: {summary.status}",
                        flush=True,
                    )
                    if not summary.can_compare:
                        raise ValueError(
                            "invalid benchmark rep; stopping instead of collecting misleading data"
                        )
        store.update("experiments", identity, status="completed")
        progress(store, identity, "completed")
    except BaseException as error:
        reason = str(error) or "interrupted"
        store.update("experiments", identity, status="aborted", abort_reason=reason)
        progress(store, identity, "aborted", reason)
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        client.close()
        render(store, identity)
        store.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--binary", default="vllm")
    parser.add_argument("--hours", type=float, default=3)
    parser.add_argument("--prompts", type=int, default=100)
    parser.add_argument("--resume")
    parser.add_argument("--startup-log")
    args = parser.parse_args()
    if not 0 < args.hours <= 3 or args.prompts < 1:
        parser.error("hours must be in (0,3] and prompts positive")
    database = Path(args.db).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    with open(str(database) + ".external.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
