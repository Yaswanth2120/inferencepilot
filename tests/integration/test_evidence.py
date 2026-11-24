import json

import pytest

from inferencepilot import env, report
from inferencepilot.fakes.selftest import mini_plan, synthetic_constraints
from inferencepilot.runner import Options, Runner
from inferencepilot.store import Store, encode


@pytest.mark.parametrize("kind", ["synthetic", "live", "unverified"])
def test_runner_persists_evidence_and_resume_preserves_it(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(env, "snapshot", lambda: {"gpu": "NVIDIA A100; not evidence of execution"})
    store = Store(tmp_path / "evidence.db")
    # No launches: this only verifies declaration/checkpoint behavior and invokes no GPU command.
    plan = mini_plan().model_copy(update={"launches": []})
    identity = Runner(store, Options(evidence=kind)).run(plan)
    saved = store.meta("evidence:" + identity)
    assert json.loads(saved)["kind"] == kind
    Runner(store, Options(evidence="live")).run(experiment=identity)
    assert store.meta("evidence:" + identity) == saved
    store.close()


def test_legacy_report_never_infers_live_from_environment(tmp_path):
    store = Store(tmp_path / "legacy.db")
    identity = store.create(mini_plan(), {"gpu": "NVIDIA A100", "vllm_version": "0.15.1"}, 1)
    bundle = report.prepare(store, identity, synthetic_constraints())
    assert bundle["evidence"]["kind"] == "unverified"
    assert "no live execution claim" in bundle["live"]
    store.set_meta("evidence:" + identity, encode({"kind": "synthetic"}))
    bundle = report.prepare(store, identity, synthetic_constraints())
    assert "not run (needs GPU)" in report.markdown(bundle)
    store.set_meta("evidence:" + identity, encode({"kind": "live"}))
    bundle = report.prepare(store, identity, synthetic_constraints())
    rendered = report.markdown(bundle)
    assert "no successful measured reps captured" in rendered
    assert "Live: not run (needs GPU)" not in rendered
    store.set_meta("evidence:" + identity, encode({"kind": "invented"}))
    with pytest.raises(ValueError, match="provenance"):
        report.prepare(store, identity, synthetic_constraints())
    store.close()


def test_telemetry_cannot_start_benchmark_after_deadline(tmp_path, monkeypatch):
    import time

    from inferencepilot.config import ConfigSpec, LoadSpec

    store = Store(tmp_path / "budget.db")
    plan = mini_plan()
    identity = store.create(plan, {"synthetic": True}, 1)
    config = store.rows("configs", experiment_id=identity, label="baseline")[0]
    launch = store.insert(
        "launches", config_id=config["id"], ordinal=1, started_at=time.time(), status="ok", cmd="[]"
    )
    runner = Runner(store)
    runner.deadline = time.time() + 10

    def slow_telemetry():
        runner.deadline = time.time() - 1
        return {"available": False, "error": "SYNTHETIC delayed telemetry"}

    monkeypatch.setattr(env, "gpu_telemetry", slow_telemetry)
    with pytest.raises(TimeoutError, match="budget exhausted"):
        runner.point(
            identity,
            launch,
            0,
            ConfigSpec(),
            plan.experiment.workloads[0],
            LoadSpec(concurrency=1),
            [42],
        )
    assert not store.rows("reps")
    store.close()
