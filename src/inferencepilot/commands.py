"""Filesystem and subprocess command handlers, kept out of argparse wiring."""

import json
import signal
import subprocess
import sys

from inferencepilot import analysis
from inferencepilot.config import ExperimentPlan
from inferencepilot.plan_commands import plan_json, run_command
from inferencepilot.planner import make_plan
from inferencepilot.runner import Options, Runner
from inferencepilot.store import Store, encode


def run(args):
    if args.dry_run:
        return run_command(args.plan, True, args.max_gpu_hours)
    if not args.db:
        raise ValueError("--db is required for execution")
    from pathlib import Path

    plan = ExperimentPlan.model_validate_json(Path(args.plan).read_text())
    if plan_json(plan) != plan_json(make_plan(plan.experiment)):
        raise ValueError("plan contents disagree with deterministic reconstruction")
    store = Store(args.db)
    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        identity = Runner(
            store,
            Options(
                binary=args.vllm_bin,
                quality_binary=args.lm_eval_bin,
                quality_limit=args.quality_limit,
            ),
        ).run(plan, budget=args.max_gpu_hours)
        print(encode(store.rows("experiments", id=identity)[0]))
        return 0 if store.rows("experiments", id=identity)[0]["status"] == "completed" else 2
    finally:
        signal.signal(signal.SIGTERM, previous)
        store.close()


def interrupt(signum, frame):
    raise KeyboardInterrupt


def database_command(args):
    store = Store(args.db)
    try:
        records = store.records(args.experiment)
        if args.command == "resume":
            options = Options(**json.loads(store.meta("options:" + args.experiment)))
            previous = signal.signal(signal.SIGTERM, interrupt)
            try:
                Runner(store, options).run(experiment=args.experiment)
            finally:
                signal.signal(signal.SIGTERM, previous)
            print(encode(store.rows("experiments", id=args.experiment)[0]))
        elif args.command == "status":
            print(
                encode(
                    {
                        **records["experiment"],
                        "launches": len(records["launches"]),
                        "reps": len(records["reps"]),
                    }
                )
            )
        else:
            print(encode(analysis.aggregate(records)))
        return 0
    finally:
        store.close()


def selftest():
    return subprocess.run(
        [sys.executable, "-m", "inferencepilot.fakes.selftest"], check=False
    ).returncode
