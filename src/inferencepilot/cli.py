"""Argument parsing and command dispatch only."""

import argparse

from inferencepilot.env import doctor, selftest_stub
from inferencepilot.plan_commands import plan_command, run_command
from inferencepilot.probe import probe_command


def main():
    parser = argparse.ArgumentParser(prog="inferencepilot")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="inspect environment without loading a model")
    check.add_argument("--vllm-bin", default="vllm")
    commands.add_parser("selftest", help="M0 wiring check; full pipeline arrives in M6")
    plan = commands.add_parser("plan", help="build a deterministic OFAT experiment plan")
    plan.add_argument("--config", required=True)
    plan.add_argument("--out", required=True)
    run = commands.add_parser("run", help="preview a plan; execution arrives in M6")
    run.add_argument("--plan", required=True)
    run.add_argument("--db")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--max-gpu-hours", type=float)
    probe = commands.add_parser("probe", help="load a variant or verify an optional factor")
    probe.add_argument("--model", required=True)
    probe.add_argument("--variant", required=True)
    probe.add_argument("--port", type=int, default=8000)
    probe.add_argument("--vllm-bin", default="vllm")
    probe.add_argument("--out")
    probe.add_argument("--startup-timeout", type=float, default=900)
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor(args.vllm_bin)
    if args.command == "plan":
        return plan_command(args.config, args.out)
    if args.command == "run":
        return run_command(args.plan, args.dry_run, args.max_gpu_hours)
    if args.command == "probe":
        return probe_command(
            args.model, args.variant, args.port, args.vllm_bin, args.out, args.startup_timeout
        )
    return selftest_stub()
