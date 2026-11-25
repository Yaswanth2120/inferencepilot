import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml

from inferencepilot.fakes.selftest import fake_path, mini_plan
from inferencepilot.store import Store

ROOT = Path(__file__).parents[2]


def test_preview_refuses_synthetic_execution(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(mini_plan().model_dump_json())
    command = ["bash", str(ROOT / "scripts/run_campaign.sh"), str(path), str(tmp_path / "never.db")]
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    preview = subprocess.run(command, capture_output=True, text=True, env=environment, check=True)
    assert "Estimated GPU hours" in preview.stdout
    refused = subprocess.run(
        [*command, "--execute"], capture_output=True, text=True, env=environment, check=False
    )
    assert refused.returncode != 0
    assert "requires measured calibration" in refused.stderr
    assert not (tmp_path / "never.db").exists()


def test_sqlite_backup_and_raw_copy(tmp_path):
    store = Store(tmp_path / "data" / "campaign.db")
    store.set_meta("checkpoint", "saved in WAL")
    store.artifact("completed.json").write_text('{"completed":true}')
    destination = tmp_path / "backup"
    environment = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/sync_results.sh"),
            str(store.path),
            str(store.path.parent),
            str(destination),
        ],
        check=True,
        capture_output=True,
        env=environment,
    )
    backup = sqlite3.connect(destination / "experiment.db")
    assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert (
        backup.execute("SELECT value FROM schema_meta WHERE key='checkpoint'").fetchone()[0]
        == "saved in WAL"
    )
    assert (destination / "data/raw/completed.json").read_text() == '{"completed":true}'
    backup.close()
    store.close()


def test_calibration_against_fake_server(tmp_path, monkeypatch):
    fake_path()
    config = tmp_path / "experiment.yaml"
    config.write_text(yaml.safe_dump(mini_plan().experiment.model_dump(mode="json")))
    output = tmp_path / "measured.yaml"
    # Invocation is explicitly fake; marking the calibration measured here tests wiring only.
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/calibrate.py"),
            "--config",
            str(config),
            "--out",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    measured = yaml.safe_load(output.read_text())
    assert measured["calibration"]["source"] == "measured"
    assert measured["calibration"]["rep_seconds"]["chat@1"] > 0
    assert "Calibration saved" in result.stdout


def test_quality_pilot_against_fake_server(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", os.environ["PATH"])
    fake_path()
    config = tmp_path / "experiment.yaml"
    config.write_text(yaml.safe_dump(mini_plan().experiment.model_dump(mode="json")))
    directory = tmp_path / "pilot"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/live_pilot.py"),
            "--config",
            str(config),
            "--out",
            str(directory),
            "--quality-limit",
            "4",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    evidence = json.loads((directory / "pilot.json").read_text())
    assert evidence["status"] == "ok"
    assert evidence["filters"]["flexible-extract"]["n"] == 4
    assert len(evidence["outputs"]) == 2
    assert evidence["launch"]["cleanup_complete"]
    assert '"status": "ok"' in result.stdout


def test_pilot_harness_failure_preserves_cleanup_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", os.environ["PATH"])
    fake_path()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    harness = binaries / "lm_eval"
    harness.write_text("#!/bin/sh\nexit 7\n")
    harness.chmod(0o755)
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.environ["PATH"])
    config = tmp_path / "experiment.yaml"
    config.write_text(yaml.safe_dump(mini_plan().experiment.model_dump(mode="json")))
    directory = tmp_path / "pilot"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/live_pilot.py"),
            "--config",
            str(config),
            "--out",
            str(directory),
            "--quality-limit",
            "4",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    evidence = json.loads((directory / "pilot.json").read_text())
    assert result.returncode != 0
    assert evidence["status"] == "failed"
    assert evidence["launch"]["cleanup_complete"]
    assert len(evidence["outputs"]) == 2
    assert "command exited 7" in result.stderr
