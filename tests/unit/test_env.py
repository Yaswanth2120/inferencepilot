import json
import subprocess

from inferencepilot import env


def test_missing_doctor(monkeypatch, capsys):
    monkeypatch.setattr(env.shutil, "which", lambda value: None)
    monkeypatch.setattr(env, "snapshot", lambda: {"gpu": {"available": False}})
    assert env.doctor("vllm") == 3
    result = json.loads(capsys.readouterr().out)
    assert "vllm not found" in result["errors"]


def test_successful_doctor(monkeypatch, capsys):
    monkeypatch.setattr(env.shutil, "which", lambda value: "/fake/" + value)
    monkeypatch.setattr(env, "snapshot", lambda: {"gpu": {"available": True}})
    monkeypatch.setattr(
        env,
        "command_output",
        lambda argv: {
            "available": True,
            "output": env.PINNED_VLLM_VERSION
            if argv[-1] == env.VERSION_FLAG
            else " ".join(flag for flags in env.USED_FLAGS.values() for flag in flags),
        },
    )
    assert env.doctor("vllm") == 0
    assert json.loads(capsys.readouterr().out)["errors"] == []


def test_command_failures():
    assert not env.command_output(["/nonexistent/inferencepilot-command"])["available"]
    assert not env.command_output(["false"])["available"]


def test_timeout(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("fake", 15)

    monkeypatch.setattr(env.subprocess, "run", timeout)
    assert not env.command_output(["fake"])["available"]


def test_snapshot_does_not_capture_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_API_KEY", "must-not-appear")
    monkeypatch.setenv("VAST_CONTAINERLABEL", "test-instance")
    monkeypatch.setattr(env, "command_output", lambda argv: {"available": True, "output": "x"})
    result = env.snapshot()
    assert len(result["pip_freeze_sha256"]) == 64
    assert result["vast"] == {"VAST_CONTAINERLABEL": "test-instance"}
    assert "must-not-appear" not in json.dumps(result)


def test_cuda_version_without_import(monkeypatch, tmp_path):
    version = tmp_path / "version.py"
    version.write_text("cuda: str | None = '12.4'\nraise RuntimeError('must not execute')\n")

    class Distribution:
        def locate_file(self, name):
            return version

    monkeypatch.setattr(env.importlib.metadata, "distribution", lambda name: Distribution())
    assert env.torch_cuda_version() == "12.4"
