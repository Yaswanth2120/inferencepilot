import signal
from pathlib import Path
from unittest.mock import Mock

import pytest

from inferencepilot import env
from inferencepilot.server import (
    CleanupError,
    LaunchResult,
    ServerManager,
    ServerTimeouts,
    log_tail,
    parse_resolved_config,
)


def test_resolved_config_provisional_fixture():
    path = Path(__file__).resolve().parents[1] / "fixtures/provisional/startup_full.log"
    resolved = parse_resolved_config(path.read_text())
    assert resolved == {
        "parser_status": "provisional",
        "raw_matched_lines": path.read_text().splitlines()[1:],
        "max_model_len": 8192,
        "prefix_caching": True,
        "chunked_prefill": True,
        "max_num_batched_tokens": 2048,
        "quantization": None,
        "enforce_eager": False,
        "kv_cache_dtype": "auto",
        "cuda_graph_mode": "FULL_AND_PIECEWISE",
        "kv_cache_tokens": 65536,
        "max_concurrency_tokens_per_request": 8192,
        "max_concurrency": 8,
        "attention_backend": "FLASH_ATTN",
    }


def test_resolved_config_real_qwen_pinned_startup():
    path = Path(__file__).resolve().parents[1] / "fixtures/real/qwen3_vllm_0151_startup.log"
    resolved = parse_resolved_config(path.read_text())
    assert resolved["max_model_len"] == 8192
    assert resolved["prefix_caching"] is True
    assert resolved["chunked_prefill"] is True
    assert resolved["max_num_batched_tokens"] == 8192
    assert resolved["quantization"] is None
    assert resolved["kv_cache_dtype"] == "auto"
    assert resolved["enforce_eager"] is False
    assert resolved["cuda_graph_mode"] == "FULL_AND_PIECEWISE"
    assert resolved["attention_backend"] == "FLASH_ATTN"
    assert resolved["kv_cache_tokens"] == 397344
    assert resolved["max_concurrency_tokens_per_request"] == 8192
    assert resolved["max_concurrency"] == 48.5
    assert resolved["raw_matched_lines"]


def test_log_overrides_unknown_fields_and_ansi():
    raw = "\x1b[32menable_prefix_caching=True, chunked_prefill_enabled=True\x1b[0m"
    resolved = parse_resolved_config(
        raw + '\n{"enable_prefix_caching": false}\n'
        "Chunked prefill is disabled\nquantization='awq_marlin'"
    )
    assert resolved["prefix_caching"] is False and resolved["chunked_prefill"] is False
    assert resolved["quantization"] == "awq_marlin"
    assert raw in resolved["raw_matched_lines"]
    assert "max_model_len" not in resolved  # No fallback to requested values.
    assert (
        parse_resolved_config("quantization='compressed-tensors'")["quantization"]
        == "compressed-tensors"
    )
    assert "cuda_graph_mode" not in parse_resolved_config("cudagraph_mode=None")
    assert parse_resolved_config("unrelated log") == {
        "parser_status": "provisional",
        "raw_matched_lines": [],
    }


def test_tail_is_last_200_lines(tmp_path):
    path = tmp_path / "log"
    path.write_text("".join(f"line {i}\n" for i in range(300)))
    assert log_tail(path).splitlines() == [f"line {i}" for i in range(100, 300)]
    assert log_tail(tmp_path / "absent") == ""


@pytest.mark.parametrize("value", [-1, 0, float("nan"), float("inf"), True])
def test_timeout_validation(value):
    with pytest.raises(ValueError):
        ServerTimeouts(readiness=value)


@pytest.mark.parametrize("memory", ["", "N/A", "-1", "nan", "0\n0"])
def test_gpu_query_rejects_unknown_or_multiple_gpus(monkeypatch, memory):
    monkeypatch.setattr(env, "command_output", lambda args: {"available": True, "output": memory})
    with pytest.raises(RuntimeError):
        env.gpu_memory_used()


def test_unavailable_safety_tools(monkeypatch):
    monkeypatch.setattr(env, "command_output", lambda args: {"available": False, "error": "absent"})
    with pytest.raises(RuntimeError, match="cannot verify GPU"):
        env.gpu_memory_used()
    with pytest.raises(RuntimeError, match="cannot inspect"):
        env.vllm_processes()
    with pytest.raises(RuntimeError, match="cannot verify process-group"):
        env.process_group_active(123)


def test_process_scan_matches_executables_not_mentions(monkeypatch):
    listing = "\n".join(
        [
            "42 python3 python3 /opt/bin/vllm serve model",
            "43 python3 python3 -m vllm.entrypoints.openai.api_server",
            "44 vllm vllm serve model",
            "45 VLLM::EngineCore VLLM::EngineCore",
            "46 python3 python3 /work/test_vllm.py",
            "47 zsh zsh -c echo vllm",
            "48 pytest pytest tests/test_vllm.py",
            "49 python3 python3 -m unrelated --vllm-bin vllm",
        ]
    )
    monkeypatch.setattr(env, "command_output", lambda args: {"available": True, "output": listing})
    assert [process["pid"] for process in env.vllm_processes()] == [42, 43, 44, 45]


def test_sigkill_escalation_and_owned_group_only(monkeypatch, tmp_path):
    manager = ServerManager(log_dir=tmp_path)
    manager.result = LaunchResult("test", [], str(tmp_path / "test.log"), 0)
    manager._group = 12345  # Simulate a group returned by our own successful Popen.
    manager._process = Mock()
    manager._wait_exit = Mock(side_effect=[False, True])
    manager._group_exists = Mock(return_value=True)
    calls = []
    monkeypatch.setattr(
        "inferencepilot.server.os.killpg", lambda pid, signum: calls.append((pid, signum))
    )
    assert manager.stop().cleanup_complete
    assert calls == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]
    manager.stop()
    assert len(calls) == 2


def test_cleanup_failure_retains_ownership(monkeypatch, tmp_path):
    manager = ServerManager(log_dir=tmp_path)
    manager.result = LaunchResult("test", [], "none", 0)
    manager._group = 12345
    manager._process = Mock()
    manager._wait_exit = Mock(return_value=False)
    manager._group_exists = Mock(return_value=True)
    monkeypatch.setattr("inferencepilot.server.os.killpg", lambda pid, signum: None)
    with pytest.raises(CleanupError, match="after SIGKILL"):
        manager.stop()
    assert not manager.result.cleanup_complete and manager._group == 12345
    assert "Cleanup failed" in manager.result.error


def test_process_scan_failure_and_secret_redaction(monkeypatch):
    monkeypatch.setattr(
        env,
        "command_output",
        lambda args: {
            "available": True,
            "output": "42 vllm vllm serve model --api-key must-not-be-recorded",
        },
    )
    assert env.vllm_processes() == [{"pid": 42, "executable": "vllm"}]
    monkeypatch.setattr(
        env,
        "command_output",
        lambda args: {
            "available": True,
            "output": "unparseable ps output",
        },
    )
    with pytest.raises(RuntimeError, match="cannot parse"):
        env.vllm_processes()


def test_group_state_uses_read_only_inspection(monkeypatch):
    monkeypatch.setattr(
        env,
        "command_output",
        lambda args: {
            "available": True,
            "output": "123 S\n456 Z\n789 R+\n",
        },
    )
    assert env.process_group_active(123)
    assert not env.process_group_active(456)  # A zombie cannot execute or hold GPU allocations.
    assert not env.process_group_active(999)


def test_live_permission_failure_is_not_ignored(monkeypatch, tmp_path):
    manager = ServerManager(log_dir=tmp_path)
    manager.result = LaunchResult("test", [], "none", 0)
    manager._group = 12345
    manager._process = Mock()
    manager._group_exists = Mock(return_value=True)

    def denied(*args):
        raise PermissionError("live group is inaccessible")

    monkeypatch.setattr("inferencepilot.server.os.killpg", denied)
    with pytest.raises(CleanupError, match="inaccessible"):
        manager.stop()
    assert not manager.result.cleanup_complete and manager._group == 12345


def test_exited_group_permission_race_is_verified(monkeypatch, tmp_path):
    manager = ServerManager(log_dir=tmp_path)
    manager._group = 12345
    manager._group_exists = Mock(side_effect=[True, False])

    def denied_after_exit(*args):
        raise PermissionError("group exited during signal")

    monkeypatch.setattr("inferencepilot.server.os.killpg", denied_after_exit)
    manager._signal_group(signal.SIGTERM)
    assert manager._group_exists.call_count == 2
