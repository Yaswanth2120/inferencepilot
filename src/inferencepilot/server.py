"""Owned serving-process lifecycle and provisional startup-log parsing."""

import math
import os
import re
import signal
import socket
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from inferencepilot.config import ConfigSpec
from inferencepilot.env import gpu_memory_used, process_group_active, vllm_errors, vllm_processes

GPU_IDLE_MIB = 2048


@dataclass(frozen=True)
class ServerTimeouts:
    readiness: float = 900
    terminate: float = 60
    kill: float = 10
    gpu_release: float = 120
    poll: float = 0.1

    def __post_init__(self):
        for name, value in vars(self).items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} timeout must be finite and positive")


@dataclass
class LaunchResult:
    id: str
    cmd: list[str]
    log_path: str
    started_at: float
    status: str = "server_failed"
    ready_at: float | None = None
    stopped_at: float | None = None
    startup_seconds: float | None = None
    resolved_args: dict = field(default_factory=dict)
    error: str | None = None
    cleanup_complete: bool = False


class CleanupError(RuntimeError):
    """Cleanup could not establish that the next launch is safe."""


def parse_resolved_config(text):
    result = {"parser_status": "provisional", "raw_matched_lines": []}
    fields = {
        "max_model_len": (r"(?:max_model_len|max_seq_len)", r"[\d,]+", int),
        "prefix_caching": (r"enable_prefix_caching", r"True|False|true|false", bool),
        "chunked_prefill": (
            r"(?:enable_chunked_prefill|chunked_prefill_enabled)",
            r"True|False|true|false",
            bool,
        ),
        "max_num_batched_tokens": (r"max_num_batched_tokens", r"[\d,]+", int),
        "quantization": (r"quantization(?:_method)?", r"[\w-]+", str),
        "kv_cache_dtype": (r"kv_cache_dtype", r"[\w]+", str),
        "enforce_eager": (r"enforce_eager", r"True|False|true|false", bool),
        "cuda_graph_mode": (
            r"cudagraph_mode",
            r"(?:<?CUDAGraphMode\.)?[A-Z_]+(?=[\s\"',}:>]|$)",
            str,
        ),
    }
    for raw_line in text.splitlines():
        line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw_line)
        matched = False
        for name, (key, value_pattern, converter) in fields.items():
            match = re.search(rf"\b{key}[\"']?\s*[=:]\s*[\"']?({value_pattern})", line)
            if match:
                value = match.group(1)
                if converter is bool:
                    value = value.lower() == "true"
                elif converter is int:
                    value = int(value.replace(",", ""))
                elif value in ("None", "null"):
                    value = None
                elif name == "cuda_graph_mode":
                    value = value.removeprefix("<").removeprefix("CUDAGraphMode.")
                result[name] = value
                matched = True
        chunk = re.search(r"Chunked prefill is (enabled|disabled)", line, re.IGNORECASE)
        if chunk:
            result["chunked_prefill"] = chunk.group(1).lower() == "enabled"
            matched = True
        cache = re.search(r"GPU KV cache size:\s*([\d,]+)\s*tokens", line)
        if cache:
            result["kv_cache_tokens"] = int(cache.group(1).replace(",", ""))
            matched = True
        concurrency = re.search(
            r"Maximum concurrency for ([\d,]+) tokens per request:\s*([\d.]+)\s*x", line
        )
        if concurrency:
            result["max_concurrency_tokens_per_request"] = int(
                concurrency.group(1).replace(",", "")
            )
            result["max_concurrency"] = float(concurrency.group(2))
            matched = True
        backend = re.search(r"Using ([\w]+) (?:attention )?backend", line)
        if backend:
            result["attention_backend"] = backend.group(1)
            matched = True
        if matched:
            result["raw_matched_lines"].append(raw_line)
    return result


def log_tail(path):
    try:
        with Path(path).open(errors="replace") as source:
            return "".join(deque(source, maxlen=200))
    except OSError:
        return ""


def preflight(spec, binary):
    try:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((spec.host, spec.port))
    except OSError as error:
        raise RuntimeError(f"port {spec.port} is not free: {error}") from error
    if gpu_memory_used() >= GPU_IDLE_MIB:
        raise RuntimeError(
            "GPU memory is busy (must be below 2048 MiB). Stop the existing server "
            "or use a non-auto-launching image; Vast.ai vastai/vllm may auto-start it."
        )
    existing = vllm_processes()
    if existing:
        raise RuntimeError(
            f"existing vllm processes: {existing}. Stop them yourself or choose a "
            "non-auto-launching image; no existing process was signalled."
        )
    errors = vllm_errors(binary)
    if errors:
        raise RuntimeError("; ".join(errors))


class ServerManager:
    def __init__(self, binary="vllm", log_dir="data/logs", timeouts=None):
        self.binary = str(binary)
        self.log_dir = Path(log_dir)
        self.timeouts = timeouts or ServerTimeouts()
        self.result = None
        self._process = None
        self._group = None
        self._log = None
        self._gpu_pending = False

    def start(self, spec, launch_id=None, load_probe=False):
        if self._group is not None or self._gpu_pending:
            raise CleanupError(
                "previous launch is not cleaned up; call stop before starting another"
            )
        spec = ConfigSpec.model_validate(spec.model_dump())
        launch_id = launch_id or uuid.uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", launch_id):
            raise ValueError("launch_id must be a plain filename-safe identifier")
        path = self.log_dir / f"{launch_id}.log"
        self.result = LaunchResult(launch_id, spec.argv(self.binary), str(path), time.time())
        started = False
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._log = path.open("x")
            preflight(spec, self.binary)
            began = time.monotonic()
            self._process = subprocess.Popen(
                self.result.cmd, stdout=self._log, stderr=self._log, start_new_session=True
            )
            self._group = self._process.pid
            self._gpu_pending = True
            started = True
            self._wait_ready(spec, began)
            self.result.ready_at = time.time()
            self.result.startup_seconds = time.monotonic() - began
            self.result.resolved_args = parse_resolved_config(path.read_text(errors="replace"))
            self.result.status = "ok"
            return self.result
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.result.status = (
                "unsupported_on_hardware" if load_probe and started else "server_failed"
            )
            self.result.error = f"{error}\nLast 200 startup log lines:\n{log_tail(path)}"
            try:
                self.stop()
            except CleanupError:
                pass  # stop records the cleanup failure and retains the next-launch safety gate.
            return self.result
        except BaseException:
            self.result.status = "aborted"
            self.result.error = "launch interrupted"
            try:
                self.stop()
            except CleanupError:
                pass
            raise

    def _wait_ready(self, spec, began):
        deadline = began + self.timeouts.readiness
        with httpx.Client(base_url=f"http://{spec.host}:{spec.port}", trust_env=False) as client:
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    raise RuntimeError(
                        f"server exited during startup with code {self._process.returncode}"
                    )
                remaining = max(0.01, min(1, (deadline - time.monotonic()) / 2))
                try:
                    health = client.get("/health", timeout=remaining)
                    models = client.get("/v1/models", timeout=remaining)
                    names = [model.get("id") for model in models.json().get("data", [])]
                    if health.is_success and models.is_success and spec.model in names:
                        if self._process.poll() is None:
                            return
                except (httpx.HTTPError, ValueError, AttributeError, TypeError):
                    pass
                time.sleep(min(self.timeouts.poll, max(0, deadline - time.monotonic())))
        raise RuntimeError("server readiness timeout (health and expected model both required)")

    def _signal_group(self, signum):
        if self._group is not None and self._group_exists():
            try:
                os.killpg(self._group, signum)
            except ProcessLookupError:
                pass
            except PermissionError:
                # The group can exit between inspection and signaling; verify, never assume.
                if self._group_exists():
                    raise

    def _group_exists(self):
        return self._group is not None and process_group_active(self._group)

    def _wait_exit(self, seconds):
        deadline = time.monotonic() + seconds
        while True:
            self._process.poll()  # Reap the parent so its zombie does not keep the group visible.
            if not self._group_exists():
                self._process.wait(timeout=self.timeouts.kill)
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(self.timeouts.poll)

    def _wait_gpu(self):
        deadline = time.monotonic() + self.timeouts.gpu_release
        while True:
            try:
                if gpu_memory_used() < GPU_IDLE_MIB:
                    self._gpu_pending = False
                    return
            except RuntimeError as error:
                raise CleanupError(str(error)) from error
            if time.monotonic() >= deadline:
                raise CleanupError(
                    "GPU memory was not released before timeout; next launch blocked"
                )
            time.sleep(self.timeouts.poll)

    def stop(self):
        if self.result is None:
            return None
        try:
            if self._group is not None:
                self._signal_group(signal.SIGTERM)
                if not self._wait_exit(self.timeouts.terminate):
                    self._signal_group(signal.SIGKILL)
                    if not self._wait_exit(self.timeouts.kill):
                        raise CleanupError("owned process group did not exit after SIGKILL")
                self._group = None
                self._process = None
            if self._log is not None:
                self._log.close()
                self._log = None
            if self._gpu_pending:
                self._wait_gpu()
            self.result.stopped_at = self.result.stopped_at or time.time()
            self.result.cleanup_complete = True
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.result.status = "server_failed"
            self.result.error = (self.result.error or "") + f"\nCleanup failed: {error}"
            raise CleanupError(str(error)) from error
        return self.result
