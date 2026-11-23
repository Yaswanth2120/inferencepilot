import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

FAKE = Path(__file__).resolve().parents[2] / "src/inferencepilot/fakes/fake_bin/vllm"


def fake_env():
    return {
        **os.environ,
        "PATH": str(Path(sys.executable).parent)
        + os.pathsep
        + str(FAKE.parent)
        + os.pathsep
        + os.environ.get("PATH", ""),
    }


def test_cli():
    result = subprocess.run(
        ["inferencepilot", "selftest"], env=fake_env(), check=False, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "Offline selftest passed" in result.stdout
    result = subprocess.run(
        ["inferencepilot", "unknown"], env=fake_env(), check=False, capture_output=True
    )
    assert result.returncode == 2


def test_fake_bench(tmp_path):
    args = [
        "vllm",
        "bench",
        "serve",
        "--num-prompts",
        "5",
        "--seed",
        "7",
        "--save-result",
        "--save-detailed",
        "--result-dir",
        str(tmp_path),
        "--result-filename",
        "result.json",
    ]
    result = subprocess.run(args, env=fake_env(), capture_output=True, text=True, check=True)
    parsed = json.loads(result.stdout)
    assert parsed == json.loads((tmp_path / "result.json").read_text())
    assert parsed["completed"] == len(parsed["ttfts"]) == len(parsed["itls"]) == 5
    assert parsed["fixture_status"] == "provisional"
    again = subprocess.run(args, env=fake_env(), capture_output=True, text=True, check=True)
    assert again.stdout == result.stdout


def test_fake_start_stream_and_sigterm(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log_path = tmp_path / "server.log"
    child_pid = None
    with log_path.open("w") as log:
        process = subprocess.Popen(
            ["vllm", "serve", "fake-model", "--port", str(port)],
            env=fake_env(),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 15
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=1) as client:
                while time.monotonic() < deadline:
                    assert process.poll() is None, log_path.read_text()
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.05)
                else:
                    pytest.fail("fake server never became ready: " + log_path.read_text())
                lines = log_path.read_text().splitlines()
                child_pid = int(
                    next(line.split("=")[1] for line in lines if line.startswith("FAKE child_pid="))
                )
                os.kill(child_pid, 0)
                assert any("PROVISIONAL resolved config:" in line for line in lines)
                assert client.get("/v1/models").json()["data"][0]["id"] == "fake-model"
                with client.stream("POST", "/v1/completions", json={"stream": True}) as stream:
                    events = list(stream.iter_lines())
                assert "data: [DONE]" in events
            process.send_signal(signal.SIGTERM)  # parent alone must clean its child
            process.wait(timeout=10)
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_fake_startup_failure():
    result = subprocess.run(
        ["vllm", "serve", "fake-model"],
        check=False,
        env={**fake_env(), "INFERENCEPILOT_FAKE_CRASH": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "injected startup crash" in result.stdout
