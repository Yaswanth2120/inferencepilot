import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferencepilot import env
from inferencepilot.config import ExperimentSpec
from inferencepilot.plan_commands import plan_json, run_command
from inferencepilot.planner import make_plan

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "src/inferencepilot/fakes/fake_bin/vllm"


def test_plan_and_dry_run(tmp_path):
    path = tmp_path / "plan.json"
    command = [
        str(Path(sys.executable).parent / "inferencepilot"),
        "plan",
        "--config",
        str(ROOT / "configs/experiment_qwen3_8b.yaml"),
        "--out",
        str(path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    digest = hashlib.sha256(path.read_bytes()).digest()
    second = subprocess.run(command, capture_output=True, text=True, check=True)
    assert hashlib.sha256(path.read_bytes()).digest() == digest
    assert first.stdout == second.stdout
    assert "Estimated GPU hours: 5.9067" in first.stdout
    preview = subprocess.run(
        [command[0], "run", "--plan", str(path), "--dry-run", "--max-gpu-hours", "1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "estimate exceeds budget cap" in preview.stdout
    assert "baseline launch=3" in preview.stdout
    assert "Synthetic calibration" in preview.stdout
    real_run = subprocess.run(
        [command[0], "run", "--plan", str(path)], capture_output=True, text=True, check=False
    )
    assert real_run.returncode == 2 and "--db is required" in real_run.stdout


def test_missing_config_errors(tmp_path):
    command = [
        str(Path(sys.executable).parent / "inferencepilot"),
        "plan",
        "--config",
        str(tmp_path / "missing.yaml"),
        "--out",
        str(tmp_path / "plan.json"),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "Configuration error" in result.stdout
    assert not (tmp_path / "plan.json").exists()


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_invalid_dry_run_budget(example, tmp_path, budget):
    path = tmp_path / "plan.json"
    path.write_text(plan_json(make_plan(ExperimentSpec.model_validate(example))))
    assert run_command(path, True, budget) == 2


def test_tampered_plan_rejected(example, tmp_path, capsys):
    path = tmp_path / "plan.json"
    plan = make_plan(ExperimentSpec.model_validate(example)).model_dump()
    plan["launches"].pop()
    path.write_text(json.dumps(plan))
    assert run_command(path, True) == 2
    assert "disagree" in capsys.readouterr().out


def test_fake_help_and_missing_flag(monkeypatch):
    monkeypatch.setenv(
        "PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    assert env.check_flags(str(FAKE)) == []
    monkeypatch.setenv("INFERENCEPILOT_FAKE_OMIT_FLAG", "--no-enable-prefix-caching")
    assert env.check_flags(str(FAKE)) == ["missing serve flag: --no-enable-prefix-caching"]


def test_doctor_with_fake_help(monkeypatch, capsys):
    monkeypatch.setenv(
        "PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    monkeypatch.setattr(env, "snapshot", lambda: {"gpu": {"available": True}})
    original_which = env.shutil.which
    monkeypatch.setattr(
        env.shutil,
        "which",
        lambda name: "/fake/lm_eval" if name == "lm_eval" else original_which(name),
    )
    assert env.doctor(str(FAKE)) == 0
    assert json.loads(capsys.readouterr().out)["errors"] == []
    monkeypatch.setenv("INFERENCEPILOT_FAKE_OMIT_FLAG", "--no-enable-chunked-prefill")
    assert env.doctor(str(FAKE)) == 3
    assert "missing serve flag" in capsys.readouterr().out


def test_wrong_version_and_help_failure(monkeypatch, capsys):
    monkeypatch.setattr(env.shutil, "which", lambda name: "/fake/" + name)
    monkeypatch.setattr(env, "snapshot", lambda: {"gpu": {"available": True}})
    monkeypatch.setattr(env, "command_output", lambda argv: {"available": True, "output": "0.0.0"})
    assert env.doctor("vllm") == 3
    assert "expected vllm 0.15.1" in capsys.readouterr().out
    monkeypatch.setattr(
        env, "command_output", lambda argv: {"available": False, "error": "timeout"}
    )
    assert env.check_flags("fake") == ["cannot inspect serve: timeout"]
