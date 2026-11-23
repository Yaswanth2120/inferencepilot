"""Generate an explicitly synthetic, fully persisted demonstration report."""

import argparse
from pathlib import Path

from inferencepilot import report
from inferencepilot.fakes.selftest import campaign, synthetic_constraints


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if (Path(args.data) / "experiment.db").exists():
        parser.error("use a fresh data directory to keep demonstrations unambiguous")
    store, identity = campaign(args.data)
    try:
        bundle = report.prepare(store, identity, synthetic_constraints())
        assert bundle["recommendation"]["chosen_config_id"]
        assert bundle["recommendation"]["rejected"]
        report.write(bundle, args.out)
        print(f"SYNTHETIC report: {args.out}; experiment={identity}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
