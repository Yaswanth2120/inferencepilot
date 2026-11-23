"""Filesystem and output handlers for planning; CLI remains wiring only."""

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from inferencepilot.config import ExperimentPlan, ExperimentSpec
from inferencepilot.planner import make_plan


def plan_json(plan):
    return (
        json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def print_schedule(plan, budget=None):
    cap = plan.experiment.max_gpu_hours if budget is None else budget
    print(f"Experiment: {plan.experiment.name}; seed={plan.experiment.seed}")
    for index, launch in enumerate(plan.launches, 1):
        print(
            f"{index:02d} {launch.config_label} launch={launch.ordinal} "
            f"points={len(launch.points)} estimated_seconds={launch.estimated_seconds:.2f}"
        )
    print(f"Estimated GPU hours: {plan.estimated_gpu_hours:.4f}; cap: {cap:.4f}")
    if plan.estimated_gpu_hours > cap:
        print("WARNING: estimate exceeds budget cap")
    for warning in plan.warnings:
        print(f"WARNING: {warning}")


def plan_command(config_path, output_path):
    try:
        experiment = ExperimentSpec.model_validate(yaml.safe_load(Path(config_path).read_text()))
        plan = make_plan(experiment)
        serialized = plan_json(plan)
        Path(output_path).write_text(serialized)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as error:
        print(f"Configuration error: {error}")
        return 2
    print_schedule(plan)
    return 0


def run_command(plan_path, dry_run, budget=None):
    if not dry_run:
        print("Execution is not implemented until M6. Use run --dry-run to inspect a plan.")
        return 2
    try:
        plan = ExperimentPlan.model_validate_json(Path(plan_path).read_text())
        # Validate derived data too: tampered or stale plans must not produce misleading previews.
        if plan_json(plan) != plan_json(make_plan(plan.experiment)):
            raise ValueError("plan contents disagree with deterministic reconstruction")
        if budget is not None and (not 0 < budget < float("inf")):
            raise ValueError("max-gpu-hours must be finite and positive")
    except (OSError, ValueError, ValidationError) as error:
        print(f"Configuration error: {error}")
        return 2
    print_schedule(plan, budget)
    return 0
