import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from inferencepilot.config import ConfigSpec
from inferencepilot.probe import run_probe
from inferencepilot.server import CleanupError, ServerManager, ServerTimeouts

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "src/inferencepilot/fakes/fake_bin/vllm"


@pytest.fixture
def fake_machine(tmp_path, monkeypatch):
    directory = tmp_path / "bin"
    directory.mkdir()
    real_ps = shutil.which("ps")
    for name, source in {
        "nvidia-smi": 'import os\nprint(os.environ.get("FAKE_GPU_MEMORY_MIB", "0"))\n',
        "ps": (
            "import os, sys\n"
            f'if sys.argv[-1] == "pgid=,stat=": os.execv({real_ps!r}, [{real_ps!r}, *sys.argv[1:]])\n'
            'print(os.environ.get("FAKE_PROCESS_LIST", ""))\n'
        ),
    }.items():
        path = directory / name
        path.write_text(f"#!{sys.executable}\n" + source)
        path.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        str(directory)
        + os.pathsep
        + str(Path(sys.executable).parent)
        + os.pathsep
        + str(FAKE.parent)
        + os.pathsep
        + os.environ.get("PATH", ""),
    )
    return directory


@pytest.fixture
def spec():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return ConfigSpec(port=port)


@pytest.fixture
def manager(fake_machine, tmp_path):
    return ServerManager(
        binary=FAKE,
        log_dir=tmp_path / "logs",
        timeouts=ServerTimeouts(readiness=5, terminate=2, kill=2, gpu_release=0.2, poll=0.02),
    )


def test_start_readiness_resolved_and_child_tree(manager, spec):
    try:
        result = manager.start(spec)
        assert result.status == "ok", result.error
        assert result.startup_seconds > 0 and result.ready_at >= result.started_at
        assert result.resolved_args["max_model_len"] == 8192
        assert result.resolved_args["attention_backend"] == "FAKE"
        assert result.resolved_args["cuda_graph_mode"] == "FULL_AND_PIECEWISE"
        child_pid = int(
            next(
                line.split("=")[1]
                for line in Path(result.log_path).read_text().splitlines()
                if line.startswith("FAKE child_pid=")
            )
        )
        os.kill(child_pid, 0)
    finally:
        manager.stop()
    assert result.cleanup_complete and result.stopped_at >= result.ready_at
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    assert manager.stop() is result  # Repeated stop does not signal again.


def test_port_busy_never_signals_external_process(manager, spec, monkeypatch):
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    signals = []
    monkeypatch.setattr("inferencepilot.server.os.killpg", lambda *args: signals.append(args))
    try:
        with socket.socket() as sock:
            sock.bind((spec.host, spec.port))
            sock.listen()
            result = manager.start(spec)
        assert result.status == "server_failed" and "not free" in result.error
        assert foreign.poll() is None and signals == []
    finally:
        foreign.terminate()
        foreign.wait(timeout=5)


def test_gpu_busy_refuses_and_stop_before_start_is_safe(manager, spec, monkeypatch):
    calls = []
    monkeypatch.setattr("inferencepilot.server.os.killpg", lambda *args: calls.append(args))
    assert manager.stop() is None
    monkeypatch.setenv("FAKE_GPU_MEMORY_MIB", "2048")
    result = manager.start(spec)
    assert result.status == "server_failed" and "GPU memory is busy" in result.error
    assert "Vast.ai" in result.error and manager._process is None and calls == []


def test_existing_vllm_process_is_not_killed(manager, spec, monkeypatch):
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setenv("FAKE_PROCESS_LIST", f"{foreign.pid} vllm vllm serve existing-model")
    try:
        result = manager.start(spec)
        assert result.status == "server_failed" and "existing vllm processes" in result.error
        assert foreign.poll() is None and manager._group is None
    finally:
        foreign.terminate()
        foreign.wait(timeout=5)


@pytest.mark.parametrize("probe", [False, True])
def test_startup_crash_tail_and_probe_classification(manager, spec, monkeypatch, probe):
    monkeypatch.setenv("INFERENCEPILOT_FAKE_CRASH", "1")
    monkeypatch.setenv("INFERENCEPILOT_FAKE_CRASH_LINES", "250")
    monkeypatch.setenv("INFERENCEPILOT_FAKE_CRASH_MESSAGE", "CUDA out of memory: injected")
    result = manager.start(spec, load_probe=probe)
    assert result.status == ("unsupported_on_hardware" if probe else "server_failed")
    assert "CUDA out of memory" in result.error
    assert "startup diagnostic 0\n" not in result.error and "startup diagnostic 249" in result.error
    assert len(result.error.split("Last 200 startup log lines:\n")[1].splitlines()) == 200
    assert result.cleanup_complete


@pytest.mark.parametrize(
    "control",
    [
        "INFERENCEPILOT_FAKE_NEVER_READY",
        "INFERENCEPILOT_FAKE_UNHEALTHY",
        "INFERENCEPILOT_FAKE_SERVED_MODEL",
    ],
)
def test_readiness_failure_cleans_child(manager, spec, monkeypatch, control):
    monkeypatch.setenv(control, "wrong-model" if control.endswith("SERVED_MODEL") else "1")
    manager.timeouts = ServerTimeouts(
        readiness=0.8, terminate=2, kill=2, gpu_release=0.2, poll=0.02
    )
    result = manager.start(spec)
    assert result.status == "server_failed" and "readiness timeout" in result.error
    assert result.cleanup_complete and manager._group is None


def test_gpu_release_timeout_blocks_next_launch(manager, spec, monkeypatch):
    result = manager.start(spec)
    assert result.status == "ok", result.error
    monkeypatch.setenv("FAKE_GPU_MEMORY_MIB", "3000")
    with pytest.raises(CleanupError, match="not released"):
        manager.stop()
    assert not result.cleanup_complete and result.status == "server_failed"
    with pytest.raises(CleanupError, match="previous launch"):
        manager.start(spec)
    monkeypatch.setenv("FAKE_GPU_MEMORY_MIB", "0")
    assert manager.stop().cleanup_complete


def test_factor_probe_records_honored_and_ignored_flags(manager, spec, monkeypatch):
    specs = [spec, ConfigSpec(port=spec.port, chunked_prefill=False)]
    result = run_probe(manager, specs, "chunked_prefill")
    assert result["status"] == "supported" and result["factor_honored"]
    monkeypatch.setenv("INFERENCEPILOT_FAKE_FORCE_CHUNKED", "1")
    result = run_probe(manager, specs, "chunked_prefill")
    assert result["status"] == "not_honored" and not result["factor_honored"]
    assert result["launches"][1]["requested"]["chunked_prefill"] is False
    assert result["launches"][1]["launch"]["resolved_args"]["chunked_prefill"] is True


def test_probe_cli_saves_evidence(fake_machine, spec, tmp_path):
    path = tmp_path / "probe.json"
    result = subprocess.run(
        [
            "inferencepilot",
            "probe",
            "--model",
            spec.model,
            "--variant",
            "bf16",
            "--port",
            str(spec.port),
            "--vllm-bin",
            str(FAKE),
            "--out",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(path.read_text())
    assert record["status"] == "supported"
    assert record["launches"][0]["launch"]["cleanup_complete"]


def test_duplicate_launch_id_does_not_overwrite(manager, spec):
    first = manager.start(spec, launch_id="fixed")
    assert first.status == "ok", first.error
    manager.stop()
    before = Path(first.log_path).read_bytes()
    second = manager.start(spec, launch_id="fixed")
    assert second.status == "server_failed"
    assert Path(first.log_path).read_bytes() == before
    assert asdict(second)["cleanup_complete"]


def test_missing_flag_refuses_before_spawn(manager, spec, monkeypatch):
    monkeypatch.setenv("INFERENCEPILOT_FAKE_OMIT_FLAG", "--no-enable-prefix-caching")
    result = manager.start(spec)
    assert result.status == "server_failed" and "missing serve flag" in result.error
    assert manager._group is None and result.cleanup_complete


def test_spawn_error_never_signals_unowned_group(manager, spec, monkeypatch):
    calls = []
    monkeypatch.setattr("inferencepilot.server.preflight", lambda spec, binary: None)

    def fail_spawn(*args, **kwargs):
        raise OSError("injected spawn failure")

    monkeypatch.setattr("inferencepilot.server.subprocess.Popen", fail_spawn)
    monkeypatch.setattr("inferencepilot.server.os.killpg", lambda *args: calls.append(args))
    result = manager.start(spec)
    assert result.status == "server_failed" and "spawn failure" in result.error
    assert result.cleanup_complete and calls == []


def test_active_launch_cannot_be_replaced(manager, spec):
    first = manager.start(spec)
    try:
        assert first.status == "ok", first.error
        with pytest.raises(CleanupError, match="previous launch"):
            manager.start(spec)
        assert manager.result is first
    finally:
        manager.stop()


def test_probe_cli_failure_keeps_log_evidence(fake_machine, spec, tmp_path, monkeypatch):
    monkeypatch.setenv("INFERENCEPILOT_FAKE_CRASH", "1")
    path = tmp_path / "failure.json"
    result = subprocess.run(
        [
            "inferencepilot",
            "probe",
            "--model",
            spec.model,
            "--variant",
            "bf16",
            "--port",
            str(spec.port),
            "--vllm-bin",
            str(FAKE),
            "--out",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    record = json.loads(path.read_text())
    assert record["launches"][0]["launch"]["status"] == "unsupported_on_hardware"
    assert "injected startup crash" in record["launches"][0]["launch"]["error"]


def test_invalid_launch_id_is_rejected(manager, spec):
    with pytest.raises(ValueError, match="filename-safe"):
        manager.start(spec, launch_id="../outside")
    assert manager._group is None


def test_interrupted_start_cleans_owned_process(manager, spec, monkeypatch):
    original_ready = manager._wait_ready

    def interrupt_after_ready(config, began):
        original_ready(config, began)
        raise KeyboardInterrupt()

    monkeypatch.setattr(manager, "_wait_ready", interrupt_after_ready)
    with pytest.raises(KeyboardInterrupt):
        manager.start(spec)
    assert manager.result.status == "aborted"
    assert manager.result.cleanup_complete and manager._group is None
