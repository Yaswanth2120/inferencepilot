#!/usr/bin/env python3
"""Owner-run baseline timing calibration. Live execution is never part of CI."""

import argparse
import json
import signal
import time
from pathlib import Path

import yaml

from inferencepilot.commands import interrupt
from inferencepilot.config import ExperimentSpec, LoadSpec
from inferencepilot.loadgen import build_command, parse_result
from inferencepilot.metrics import summarize
from inferencepilot.runner import execute
from inferencepilot.server import ServerManager
from inferencepilot.store import Store


def calibrate(config, output, binary="vllm"):
    experiment = ExperimentSpec.model_validate(yaml.safe_load(Path(config).read_text()))
    destination = Path(output)
    if destination.exists():
        raise ValueError("calibration output exists; use a fresh output path")
    store = Store(destination.parent / "calibration.db")
    manager = ServerManager(binary=binary, log_dir=destination.parent / "calibration-logs")
    durations = {}
    try:
        launch = manager.start(experiment.baseline)
        if launch.status != "ok":
            raise ValueError(f"calibration startup failed: {launch.error}")
        for workload in experiment.workloads:
            for concurrency in workload.concurrency:
                path = store.artifact(f"calibration-{launch.id}-{workload.name}-{concurrency}.json")
                command = build_command(
                    experiment.baseline,
                    workload,
                    LoadSpec(concurrency=concurrency),
                    experiment.seed,
                    path,
                    binary=binary,
                )
                execute(command, path.with_suffix(".log"), 3600)
                result = parse_result(json.loads(path.read_text()))
                summary = summarize(result, workload.output_tokens)
                if not summary.can_compare:
                    raise ValueError("calibration rep failed or was partial")
                durations[f"{workload.name}@{concurrency}"] = result.duration_s
    finally:
        started = time.monotonic()
        manager.stop()
        teardown = time.monotonic() - started
        store.close()
    measured = experiment.model_dump(mode="json")
    measured["calibration"] = dict(
        source="measured",
        note=f"One baseline rep per point; raw artifacts under {destination.parent}/raw; reserve covers open-loop and quality, actual runtime may vary.",
        startup_seconds=launch.startup_seconds,
        teardown_seconds=teardown,
        rep_seconds=durations,
        extra_seconds=3600,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(measured, sort_keys=False))
    print(
        f"Calibration saved: {destination}. Review the estimate and quality/open-loop reserve before execution."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--vllm-bin", default="vllm")
    args = parser.parse_args()
    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        calibrate(args.config, args.out, args.vllm_bin)
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
