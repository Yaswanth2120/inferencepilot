"""Best-effort environment inspection without importing GPU libraries."""

import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from inferencepilot.vllm_flags import HELP_ALL_FLAG, PINNED_VLLM_VERSION, USED_FLAGS, VERSION_FLAG


def command_output(argv):
    """Return bounded command output, or an explicit unavailable reason."""
    try:
        result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "error": str(error)}
    if result.returncode:
        return {"available": False, "error": result.stderr.strip() or "command failed"}
    return {"available": True, "output": result.stdout.strip()}


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def host_ram_bytes():
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        result = command_output(["sysctl", "-n", "hw.memsize"])
        if result["available"] and result["output"].isdigit():
            return int(result["output"])
        return None


def torch_cuda_version():
    try:
        distribution = importlib.metadata.distribution("torch")
        source = Path(distribution.locate_file("torch/version.py")).read_text()
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign):
                names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names = [node.target.id]
            else:
                continue
            if "cuda" in names:
                return ast.literal_eval(node.value)
    except (importlib.metadata.PackageNotFoundError, OSError, SyntaxError, ValueError):
        pass
    return None


def cpu_model():
    if platform.system() == "Darwin":
        result = command_output(["sysctl", "-n", "machdep.cpu.brand_string"])
        if result["available"]:
            return result["output"]
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def snapshot():
    frozen = command_output([os.sys.executable, "-m", "pip", "freeze"])
    gpu = command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,compute_cap,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    cuda = command_output(["nvidia-smi"])
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": cpu_model(),
        "ram_bytes": host_ram_bytes(),
        "vllm_version": package_version("vllm"),
        "torch_version": package_version("torch"),
        "lm_eval_version": package_version("lm_eval"),
        "gpu": gpu,
        "cuda_driver_report": cuda,
        "cuda_runtime_version": torch_cuda_version(),
        "cuda_runtime_note": "read from torch/version.py without importing torch; null if unavailable",
        "git": command_output(["git", "rev-parse", "HEAD"]),
        "pip_freeze_sha256": hashlib.sha256(frozen["output"].encode()).hexdigest()
        if frozen["available"]
        else None,
        "vast": {
            key: os.environ[key]
            for key in ("VAST_CONTAINERLABEL", "VAST_INSTANCE_ID")
            if key in os.environ
        },
    }


def check_flags(binary):
    for command, flags in USED_FLAGS.items():
        result = command_output([binary, *command.split(), HELP_ALL_FLAG])
        if not result["available"]:
            return [f"cannot inspect {command}: {result['error']}"]
        present = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", result["output"]))
        missing = sorted(set(flags) - present)
        if missing:
            return [f"missing {command} flag: {flag}" for flag in missing]
    return []


def doctor(vllm_bin):
    checks = []
    binary = shutil.which(vllm_bin)
    if binary is None:
        checks.append("vllm not found")
    else:
        version = command_output([binary, VERSION_FLAG])
        if not version["available"]:
            checks.append("cannot read vllm version")
        elif PINNED_VLLM_VERSION not in version["output"].split():
            checks.append(f"expected vllm {PINNED_VLLM_VERSION}; got {version['output']}")
        checks.extend(check_flags(binary))
    environment = snapshot()
    if not environment["gpu"]["available"]:
        checks.append("nvidia-smi unavailable or failed")
    if shutil.which("lm_eval") is None:
        checks.append("lm-eval executable not found")
    print(
        json.dumps(
            {
                "environment": environment,
                "errors": checks,
                "flag_check": {"version": PINNED_VLLM_VERSION, "commands": list(USED_FLAGS)},
            },
            indent=2,
        )
    )
    return 3 if checks else 0


def selftest_stub():
    print("M0 CLI wiring OK. Full fake-server pipeline selftest is pending M6.")
    return 0
