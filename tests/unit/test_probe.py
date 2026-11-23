from unittest.mock import Mock

import pytest

from inferencepilot.config import VARIANTS, ConfigSpec
from inferencepilot.probe import probe_command, probe_specs, run_probe
from inferencepilot.server import CleanupError, LaunchResult


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_probe_variant_spec(variant):
    model, quantization = VARIANTS[variant]
    specs = probe_specs(model, variant, 8000)
    assert len(specs) == 1 and specs[0].quantization == quantization


def test_optional_probe_specs():
    model = VARIANTS["bf16"][0]
    assert [spec.chunked_prefill for spec in probe_specs(model, "chunked_prefill", 8000)] == [
        True,
        False,
    ]
    assert probe_specs(model, "kv_cache_fp8", 8000)[0].kv_cache_dtype == "fp8"
    with pytest.raises(ValueError, match="unknown"):
        probe_specs(model, "unknown", 8000)


def test_cleanup_failure_preserves_evidence_and_stops_following_probes():
    manager = Mock()
    manager.start.return_value = LaunchResult("failed", [], "log", 0, error="GPU release failed")
    manager.stop.side_effect = CleanupError("GPU release failed")
    result = run_probe(
        manager, [ConfigSpec(), ConfigSpec(chunked_prefill=False)], "chunked_prefill"
    )
    assert manager.start.call_count == 1
    assert result["status"] == "probe_failed" and not result["factor_honored"]
    assert "GPU release failed" in result["launches"][0]["launch"]["error"]
    with pytest.raises(ValueError, match="at least one"):
        run_probe(manager, [], "bf16")


def test_invalid_or_existing_probe_output_never_starts(tmp_path, monkeypatch):
    path = tmp_path / "existing.json"
    path.write_text("keep")
    create_manager = Mock()
    monkeypatch.setattr("inferencepilot.probe.ServerManager", create_manager)
    assert probe_command("bad-model", "bf16", out=path) == 2
    assert probe_command(VARIANTS["bf16"][0], "bf16", out=path) == 2
    assert not create_manager.called and path.read_text() == "keep"
