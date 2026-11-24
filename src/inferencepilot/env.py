"""Best-effort environment inspection without importing GPU libraries."""

import ast
import hashlib
import importlib.metadata
import json
import math
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


def vllm_errors(vllm_bin):
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
    return checks


def doctor(vllm_bin):
    checks = vllm_errors(vllm_bin)
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


def gpu_memory_used():
    result = command_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ]
    )
    if not result["available"]:
        raise RuntimeError(f"cannot verify GPU memory: {result['error']}")
    rows = result["output"].splitlines()
    if len(rows) != 1:
        raise RuntimeError("exactly one visible GPU is required")
    try:
        memory = float(rows[0])
    except ValueError as error:
        raise RuntimeError("invalid nvidia-smi memory.used output") from error
    if not math.isfinite(memory) or memory < 0:
        raise RuntimeError("invalid nvidia-smi memory.used output")
    return memory


def vllm_processes():
    result = command_output(["ps", "-eo", "pid=,comm=,args="])
    if not result["available"]:
        raise RuntimeError(f"cannot inspect serving processes: {result['error']}")
    found = []
    for line in result["output"].splitlines():
        parts = line.strip().split(maxsplit=2)
        if not line.strip():
            continue
        if len(parts) != 3 or not parts[0].isdigit():
            raise RuntimeError("cannot parse serving-process inspection output")
        pid, executable, arguments = parts
        tokens = arguments.split()
        name = Path(executable).name
        is_vllm = name == "vllm" or name.startswith("VLLM::")
        if tokens:
            is_vllm |= Path(tokens[0]).name == "vllm" or tokens[0].startswith("VLLM::")
        if name.lower().startswith("python") and len(tokens) > 1:
            is_vllm |= Path(tokens[1]).name == "vllm"
            if len(tokens) > 2 and tokens[1] == "-m":
                is_vllm |= tokens[2] == "vllm" or tokens[2].startswith("vllm.")
        if is_vllm and int(pid) != os.getpid():
            found.append({"pid": int(pid), "executable": name})
    return found


def process_group_active(group):
    result = command_output(["ps", "-eo", "pgid=,stat="])
    if not result["available"]:
        raise RuntimeError(f"cannot verify process-group exit: {result['error']}")
    for line in result["output"].splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[0].isdigit():
            raise RuntimeError("cannot parse process-group inspection output")
        if int(parts[0]) == group and not parts[1].startswith("Z"):
            return True
    return False


def gpu_telemetry():
    """Sample supported GPU fields; missing diagnostics never become fabricated zeroes."""
    import csv
    import time

    names = (
        "memory_used_mib",
        "sm_clock_mhz",
        "memory_clock_mhz",
        "power_w",
        "temperature_c",
        "utilization_pct",
    )
    sample = dict(
        sampled_at=time.time(), available=False, values=dict.fromkeys(names), unsupported=[]
    )
    result = command_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,clocks.sm,clocks.mem,power.draw,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    if not result["available"]:
        return {**sample, "error": result.get("error", "GPU telemetry unavailable")}
    rows = list(csv.reader(result["output"].splitlines()))
    if len(rows) != 1 or len(rows[0]) != len(names):
        return {**sample, "error": "telemetry requires exactly one GPU and six fields"}
    for name, raw in zip(names, rows[0]):
        raw = raw.strip()
        if raw.lower() in ("n/a", "[n/a]", "not supported", "[not supported]"):
            sample["unsupported"].append(name)
            continue
        try:
            value = float(raw)
        except ValueError:
            return {**sample, "error": f"invalid telemetry value for {name}"}
        if not math.isfinite(value) or value < 0 or (name == "utilization_pct" and value > 100):
            return {**sample, "error": f"invalid telemetry range for {name}"}
        sample["values"][name] = value
    sample["available"] = True
    return sample
