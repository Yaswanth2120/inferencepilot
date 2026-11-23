"""Explicitly synthetic, offline campaign; production modules never import fakes."""

import os
import socket
import sys
import tempfile
from pathlib import Path

from inferencepilot.config import ExperimentSpec
from inferencepilot.planner import make_plan
from inferencepilot.runner import Options, Runner
from inferencepilot.server import ServerTimeouts
from inferencepilot.store import Store


def mini_plan():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return make_plan(
        ExperimentSpec.model_validate(
            dict(
                name="SYNTHETIC offline selftest",
                baseline={"port": port},
                seed=42,
                factors=dict(
                    variants=["bf16"],
                    prefix_caching=[True, False],
                    max_num_batched_tokens=[8192],
                    max_num_seqs=[256],
                    chunked_prefill=[True],
                    kv_cache_dtype=["auto"],
                ),
                workloads=[
                    dict(
                        name="chat",
                        dataset="random",
                        input_tokens=8,
                        output_tokens=4,
                        concurrency=[1],
                        num_prompts=2,
                        warmups=1,
                    )
                ],
                calibration=dict(
                    source="synthetic",
                    note="offline only",
                    startup_seconds=1,
                    teardown_seconds=1,
                    rep_seconds={"chat@1": 0.1},
                    extra_seconds=1,
                ),
            )
        )
    )


def fake_path():
    directory = Path(__file__).parent / "fake_bin"
    os.environ["PATH"] = (
        str(directory)
        + os.pathsep
        + str(Path(sys.executable).parent)
        + os.pathsep
        + os.environ["PATH"]
    )
    return directory


def campaign(directory):
    binaries = fake_path()
    store = Store(Path(directory) / "experiment.db")
    options = Options(
        binary=str(binaries / "vllm"),
        quality_binary=str(binaries / "lm_eval"),
        quality_limit=4,
        agreement_count=2,
        agreement_tokens=3,
        timeouts=ServerTimeouts(readiness=10, terminate=5, kill=3, gpu_release=3, poll=0.05),
    )
    identity = Runner(store, options).run(mini_plan())
    assert store.rows("experiments", id=identity)[0]["status"] == "completed"
    assert len(store.records(identity)["reps"]) == 120
    Runner(store, options).run(experiment=identity)
    assert len(store.records(identity)["reps"]) == 120
    return store, identity


def main():
    with tempfile.TemporaryDirectory(prefix="inferencepilot-selftest-") as directory:
        store, identity = campaign(directory)
        records = store.records(identity)
        assert len([launch for launch in records["launches"] if launch["status"] == "ok"]) == 6
        assert len(records["quality"]) == 6
        assert len(records["agreement"]) == 5
        store.close()
    print(
        "Offline selftest passed: 6 launches, 120 reps, quality, agreement, idempotent resume. SYNTHETIC; live: not run (needs GPU)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
