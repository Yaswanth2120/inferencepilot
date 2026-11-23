"""Argument parsing and command dispatch only."""

import argparse

from inferencepilot import commands as handlers
from inferencepilot.env import doctor
from inferencepilot.plan_commands import plan_command
from inferencepilot.probe import probe_command


def dispatch():
    parser = argparse.ArgumentParser(prog="inferencepilot")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="inspect environment without loading a model")
    check.add_argument("--vllm-bin", default="vllm")
    commands.add_parser("selftest", help="complete offline fake campaign")
    plan = commands.add_parser("plan", help="build a deterministic OFAT experiment plan")
    plan.add_argument("--config", required=True)
    plan.add_argument("--out", required=True)
    run = commands.add_parser("run", help="execute or preview a plan")
    run.add_argument("--plan", required=True)
    run.add_argument("--db")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--max-gpu-hours", type=float)
    run.add_argument("--vllm-bin", default="vllm")
    run.add_argument("--lm-eval-bin", default="lm_eval")
    run.add_argument("--quality-limit", type=int)
    for name in ("resume", "status", "analyze", "regress", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--db", required=True)
        command.add_argument("--experiment", required=True)
        if name == "regress":
            command.add_argument("--baseline", default="baseline")
            command.add_argument("--min-effect-pct", type=float, default=5)
    power = commands.add_parser("power")
    power.add_argument("--out", required=True)
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
        return handlers.run(args)
    if args.command == "probe":
        return probe_command(
            args.model, args.variant, args.port, args.vllm_bin, args.out, args.startup_timeout
        )
    if args.command in ("resume", "status", "analyze", "regress", "validate"):
        return handlers.database_command(args)
    if args.command == "power":
        return handlers.power(args.out)
    return handlers.selftest()


def main():
    try:
        return dispatch()
    except (ValueError, OSError, IndexError) as error:
        print(f"Configuration error: {error}")
        return 2
