"""Argument parsing and command dispatch only."""

import argparse

from inferencepilot.env import doctor, selftest_stub


def main():
    parser = argparse.ArgumentParser(prog="inferencepilot")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="inspect environment without loading a model")
    check.add_argument("--vllm-bin", default="vllm")
    commands.add_parser("selftest", help="M0 wiring check; full pipeline arrives in M6")
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor(args.vllm_bin)
    return selftest_stub()
