#!/usr/bin/env python3
"""Check real quality and token-ID paths before committing to a long campaign."""

import argparse
import asyncio
import json
import signal
import time
from dataclasses import asdict
from pathlib import Path

import yaml

from inferencepilot import quality
from inferencepilot.commands import interrupt
from inferencepilot.config import ExperimentSpec
from inferencepilot.runner import execute
from inferencepilot.server import ServerManager


def pilot(config, output, limit=16):
    """Save a small harness evaluation and token outputs from one owned baseline launch."""
    experiment = ExperimentSpec.model_validate(yaml.safe_load(Path(config).read_text()))
    spec = experiment.baseline
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    manager = ServerManager(log_dir=directory / "logs")
    result = {"status": "failed", "quality_limit": limit}
    try:
        launch = manager.start(spec)
        if launch.status != "ok":
            raise RuntimeError(f"pilot startup failed: {launch.error}")
        started = time.monotonic()
        outputs, _ = asyncio.run(
            quality.agreement_check(
                f"http://127.0.0.1:{spec.port}",
                spec.model,
                prompts=quality.fixed_prompts()[:2],
                seed=spec.seed,
            )
        )
        result["agreement_seconds"] = time.monotonic() - started
        result["outputs"] = outputs
        started = time.monotonic()
        execute(
            quality.quality_command(spec.model, spec.port, directory / "quality", limit, spec.seed),
            directory / "harness.log",
            1800,
        )
        paths = list((directory / "quality").rglob("*samples*gsm8k*.jsonl"))
        if len(paths) != 1:
            raise ValueError("expected exactly one gsm8k sample log")
        samples = quality.read_samples(paths[0], limit)
        result.update(
            status="ok",
            quality_seconds=time.monotonic() - started,
            filters=quality.quality_summary(samples),
            samples_path=str(paths[0]),
        )
    finally:
        try:
            manager.stop()
        finally:
            if manager.result is not None:
                result["launch"] = asdict(manager.result)
                if not manager.result.cleanup_complete:
                    result["status"] = "failed"
            (directory / "pilot.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    """Parse pilot inputs and turn SIGTERM into owned-server cleanup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--quality-limit", type=int, default=16, choices=range(1, 1320))
    args = parser.parse_args()
    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        result = pilot(args.config, args.out, args.quality_limit)
        print(json.dumps({key: result[key] for key in ("status", "quality_seconds")}))
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
