import json
import time

import pytest

from inferencepilot import analysis
from inferencepilot import runner as runner_module
from inferencepilot.config import ConfigSpec
from inferencepilot.fakes.selftest import fake_path, mini_plan
from inferencepilot.runner import Options, Runner
from inferencepilot.store import Store, encode


def setup_quality(tmp_path):
    binaries = fake_path()
    store = Store(tmp_path / "quality.db")
    identity = store.create(mini_plan(), {"synthetic": True}, 1)
    runner = Runner(
        store,
        Options(evidence="synthetic", quality_binary=str(binaries / "lm_eval"), quality_limit=4),
    )
    runner.deadline = time.time() + 60
    return store, identity, runner


def launch_for(store, experiment, label, role, spec):
    configs = store.rows("configs", experiment_id=experiment, label=label)
    if configs:
        config = configs[0]
    else:
        config_id = store.insert(
            "configs",
            experiment_id=experiment,
            label=label,
            role=role,
            spec=encode(spec.model_dump()),
            spec_hash="synthetic-test",
        )
        config = store.rows("configs", id=config_id)[0]
    ordinal = len(store.rows("launches", config_id=config["id"])) + 1
    launch = store.insert(
        "launches",
        config_id=config["id"],
        ordinal=ordinal,
        started_at=time.time(),
        status="ok",
        cmd="[]",
        resolved_args='{"raw_matched_lines":["SYNTHETIC"]}',
    )
    return launch, config


def test_quality_measures_precision_and_combined_but_reuses_scheduling(tmp_path, monkeypatch):
    store, identity, runner = setup_quality(tmp_path)
    commands = []
    execute = runner_module.execute

    def tracked(argv, log, timeout):
        commands.append(argv)
        return execute(argv, log, timeout)

    monkeypatch.setattr(runner_module, "execute", tracked)
    cases = [
        ("baseline", "baseline", ConfigSpec()),
        ("prefix_caching-false", "candidate", ConfigSpec(prefix_caching=False)),
        ("seeded-eager", "seeded_regression", ConfigSpec(enforce_eager=True)),
        ("baseline", "baseline", ConfigSpec()),
        ("combined", "combined", ConfigSpec()),
        ("weights-fp8_online", "candidate", ConfigSpec(variant="fp8_online", quantization="fp8")),
        ("kv-fp8", "candidate", ConfigSpec(kv_cache_dtype="fp8")),
    ]
    for label, role, spec in cases:
        launch, config = launch_for(store, identity, label, role, spec)
        runner.evaluate_gsm8k(identity, launch, spec, config)
    rows = store.records(identity)["quality"]
    measured = [row for row in rows if not json.loads(row["metrics"])["inherited"]]
    inherited = [row for row in rows if json.loads(row["metrics"])["inherited"]]
    assert len(commands) == len(measured) == 4
    assert len(inherited) == 3
    baseline_row = next(
        row
        for row in measured
        if row["launch_id"]
        == store.rows(
            "launches",
            config_id=store.rows("configs", experiment_id=identity, label="baseline")[0]["id"],
        )[0]["id"]
    )
    for row in inherited:
        metrics = json.loads(row["metrics"])
        assert metrics["source_quality_id"] == baseline_row["id"]
        assert metrics["source_launch_id"] == baseline_row["launch_id"]
        assert row["samples_path"] == baseline_row["samples_path"]
        assert metrics["paired"]["flexible-extract"]["mcnemar_p"] == 1
        assert row["n"] == 4
    # Retrying an interrupted combined launch reuses that combined result, never the baseline's.
    launch, config = launch_for(store, identity, "combined", "combined", ConfigSpec())
    runner.evaluate_gsm8k(identity, launch, ConfigSpec(), config)
    assert len(commands) == 4
    combined_source = store.rows("quality_results", launch_id=launch)[0]
    assert json.loads(combined_source["metrics"])["source_quality_id"] != baseline_row["id"]
    inputs = analysis.recommendation_inputs(store.records(identity), [], [])
    scheduling = next(row for row in inputs if row["label"] == "prefix_caching-false")
    assert scheduling["quality"]["source"]["inherited"]
    assert scheduling["quality"]["source"]["quality_id"] == baseline_row["id"]
    store.close()


def test_failed_quality_is_not_reused_and_baseline_pointer_recovers(tmp_path, monkeypatch):
    store, identity, runner = setup_quality(tmp_path)
    execute = runner_module.execute
    calls = []

    def failing_once(argv, log, timeout):
        calls.append(argv)
        if len(calls) == 1:
            raise ValueError("SYNTHETIC harness failure")
        return execute(argv, log, timeout)

    monkeypatch.setattr(runner_module, "execute", failing_once)
    for _ in range(2):
        launch, config = launch_for(store, identity, "baseline", "baseline", ConfigSpec())
        runner.evaluate_gsm8k(identity, launch, ConfigSpec(), config)
    assert len(calls) == 2
    rows = store.records(identity)["quality"]
    assert sorted(row["n"] for row in rows) == [0, 4]
    # Simulate an interrupt after the atomic successful-result/cache commit but before
    # recording the first-baseline path. The saved successful source is sufficient.
    store.set_meta("quality_baseline:" + identity, "")
    launch, config = launch_for(store, identity, "baseline", "baseline", ConfigSpec())
    runner.evaluate_gsm8k(identity, launch, ConfigSpec(), config)
    assert len(calls) == 2
    assert json.loads(store.rows("quality_results", launch_id=launch)[0]["metrics"])["inherited"]
    store.close()


def test_atomic_quality_checkpoint_does_not_cache_failed_insert(tmp_path):
    import sqlite3

    store = Store(tmp_path / "atomic.db")
    with pytest.raises(sqlite3.IntegrityError):
        store.checkpoint_quality(
            "cache-key",
            launch_id="missing",
            task="gsm8k",
            n=4,
            metrics="{}",
            created_at=time.time(),
        )
    assert store.meta("cache-key") is None
    assert not store.rows("quality_results")
    store.close()
