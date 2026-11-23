import json
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferencepilot.fakes.selftest import fake_path, mini_plan
from inferencepilot.runner import Options, Runner
from inferencepilot.server import ServerTimeouts
from inferencepilot.store import SCHEMA, Store


def test_schema_version_and_foreign_keys(tmp_path):
    store = Store(tmp_path / "schema.db")
    # Exact source DDL is the contract, including unique constraints and indexes.
    assert (
        SCHEMA
        == (Path(__file__).parents[2] / "AGENTS.md")
        .read_text()
        .split("```sql\n")[1]
        .split("```")[0]
    )
    assert store.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    with pytest.raises(sqlite3.IntegrityError):
        store.insert(
            "configs",
            experiment_id="missing",
            label="bad",
            role="baseline",
            spec="{}",
            spec_hash="x",
        )
    with pytest.raises(ValueError):
        store.rows("configs; DROP TABLE configs")
    store.set_meta("version", "999")
    store.close()
    with pytest.raises(ValueError, match="schema version mismatch"):
        Store(tmp_path / "schema.db")


def test_interrupt_resume(tmp_path, monkeypatch):
    fake_path()
    plan = mini_plan()
    path = tmp_path / "plan.json"
    path.write_text(plan.model_dump_json())
    db = tmp_path / "campaign.db"
    process = subprocess.Popen(
        [
            str(Path(sys.executable).parent / "inferencepilot"),
            "run",
            "--plan",
            str(path),
            "--db",
            str(db),
            "--quality-limit",
            "4",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            assert process.poll() is None
            try:
                connection = sqlite3.connect(db)
                count = connection.execute("SELECT count(*) FROM reps").fetchone()[0]
                connection.close()
                if count >= 2:
                    break
            except sqlite3.OperationalError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("no checkpoint before timeout")
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=15)
        store = Store(db)
        identity = store.rows("experiments")[0]["id"]
        before = {r["id"]: r for r in store.records(identity)["reps"]}
        assert store.rows("experiments")[0]["status"] == "aborted"
        options = Options(
            quality_limit=4,
            agreement_count=2,
            agreement_tokens=3,
            timeouts=ServerTimeouts(readiness=10, terminate=5, kill=3, gpu_release=3, poll=0.05),
        )
        Runner(store, options).run(experiment=identity)
        records = store.records(identity)
        assert records["experiment"]["status"] == "completed"
        assert len(records["reps"]) == 120
        assert all(rep in {r["id"] for r in records["reps"]} for rep in before)
        seen = set()
        points = {p["id"]: p for p in records["points"]}
        for rep in records["reps"]:
            point = points[rep["point_id"]]
            params = json.loads(point["params"])
            assert rep["seed"] == params["seeds"][rep["rep"]]
            key = (
                params["slot"],
                point["workload"],
                point["mode"],
                point["concurrency"],
                point["request_rate"],
                rep["rep"],
            )
            assert key not in seen
            seen.add(key)
        assert len(records["quality"]) == 6
        assert len(records["agreement"]) == 5
        store.close()
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=15)


def test_budget_and_server_failure(tmp_path, monkeypatch):
    fake_path()
    store = Store(tmp_path / "budget.db")
    identity = Runner(store).run(mini_plan(), budget=1e-12)
    assert store.rows("experiments", id=identity)[0]["status"] == "aborted"
    assert "budget exhausted" in store.rows("experiments", id=identity)[0]["abort_reason"]
    monkeypatch.setenv("INFERENCEPILOT_FAKE_CRASH", "1")
    identity = Runner(store).run(mini_plan())
    records = store.records(identity)
    assert records["experiment"]["status"] == "completed"
    assert len(records["launches"]) == 6
    assert all(row["status"] == "server_failed" for row in records["launches"])
    store.close()


def test_resume_completed_after_deadline(tmp_path):
    store = Store(tmp_path / "completed.db")
    identity = store.create(mini_plan(), {"synthetic": True}, 1)
    store.update("experiments", identity, status="completed", created_at=0)
    assert Runner(store).run(experiment=identity) == identity
    assert store.rows("experiments", id=identity)[0]["status"] == "completed"
    store.close()


def test_agreement_is_cancelled_at_budget(tmp_path, monkeypatch):
    import asyncio

    from inferencepilot import quality
    from inferencepilot.config import ConfigSpec

    async def hanging(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(quality, "agreement_check", hanging)
    store = Store(tmp_path / "deadline.db")
    runner = Runner(store)
    runner.deadline = time.time() + 0.02
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(runner.collect_agreement(ConfigSpec(), None))
    store.close()
