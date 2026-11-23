"""Persist load and factor probe results; never import the fake implementation."""

import json
import uuid
from dataclasses import asdict
from pathlib import Path

from pydantic import ValidationError

from inferencepilot.config import VARIANTS, ConfigSpec
from inferencepilot.server import CleanupError, ServerManager, ServerTimeouts


def probe_specs(model, variant, port):
    if variant in VARIANTS:
        quantization = VARIANTS[variant][1]
        return [ConfigSpec(model=model, variant=variant, quantization=quantization, port=port)]
    if variant == "chunked_prefill":
        return [
            ConfigSpec(model=model, port=port, chunked_prefill=value) for value in (True, False)
        ]
    if variant == "kv_cache_fp8":
        return [ConfigSpec(model=model, port=port, kv_cache_dtype="fp8")]
    raise ValueError(f"unknown probe variant: {variant}")


def run_probe(manager, specs, variant):
    if not specs:
        raise ValueError("at least one probe configuration required")
    launches = []
    for spec in specs:
        try:
            launch = manager.start(spec, load_probe=True)
        finally:
            try:
                manager.stop()
            except CleanupError:
                pass  # Preserve the recorded failure instead of losing probe evidence.
        launches.append({"requested": spec.model_dump(), "launch": asdict(launch)})
        if not launch.cleanup_complete:
            break
    supported = len(launches) == len(specs) and all(
        entry["launch"]["status"] == "ok" for entry in launches
    )

    payload = {
        "variant": variant,
        "status": "supported" if supported else "probe_failed",
        "parser_status": "provisional",
        "launches": launches,
    }
    if variant in ("chunked_prefill", "kv_cache_fp8"):
        field = "chunked_prefill" if variant == "chunked_prefill" else "kv_cache_dtype"
        honored = supported and all(
            entry["launch"]["resolved_args"].get(field) == entry["requested"][field]
            for entry in launches
        )
        payload["factor_honored"] = honored
        if supported and not honored:
            payload["status"] = "not_honored"
    return payload


def probe_command(model, variant, port=8000, binary="vllm", out=None, startup_timeout=900):
    try:
        specs = probe_specs(model, variant, port)
        timeouts = ServerTimeouts(readiness=startup_timeout)
        path = Path(out) if out else Path("data/probes") / f"{uuid.uuid4().hex}.json"
        if path.exists():
            raise FileExistsError(f"probe output already exists: {path}")
        payload = run_probe(ServerManager(binary=binary, timeouts=timeouts), specs, variant)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as output:
            json.dump(payload, output, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, RuntimeError, ValidationError) as error:
        print(f"Probe error: {error}")
        return 2 if isinstance(error, (ValueError, OSError)) else 3
    print(json.dumps({"status": payload["status"], "out": str(path)}))
    return 0 if payload["status"] == "supported" else 3
