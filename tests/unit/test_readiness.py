import pytest

from inferencepilot import env, quality, report
from inferencepilot.config import ConfigSpec


def test_full_gpu_telemetry(monkeypatch):
    commands = []

    def output(argv):
        commands.append(argv)
        return {"available": True, "output": "123, 1410, 1593, 210.5, 45, 97"}

    monkeypatch.setattr(env, "command_output", output)
    sample = env.gpu_telemetry()
    assert sample["available"]
    assert sample["values"] == dict(
        memory_used_mib=123,
        sm_clock_mhz=1410,
        memory_clock_mhz=1593,
        power_w=210.5,
        temperature_c=45,
        utilization_pct=97,
    )
    assert sample["sampled_at"] > 0
    assert "clocks.sm" in commands[0][1]


@pytest.mark.parametrize(
    "raw,available",
    [
        ("0, [N/A], 1000, N/A, 40, 0", True),
        ("0, 1, 2, inf, 40, 1", False),
        ("0, 1, 2, 3, 40, 101", False),
        ("0, 1", False),
        ("0, 1, 2, 3, 40, 1\n0, 1, 2, 3, 40, 1", False),
    ],
)
def test_missing_or_invalid_telemetry(monkeypatch, raw, available):
    monkeypatch.setattr(env, "command_output", lambda argv: {"available": True, "output": raw})
    sample = env.gpu_telemetry()
    assert sample["available"] is available
    if available:
        assert sample["values"]["sm_clock_mhz"] is None
        assert sample["values"]["power_w"] is None
        assert sample["unsupported"] == ["sm_clock_mhz", "power_w"]
    else:
        assert sample["error"]


def test_unavailable_telemetry(monkeypatch):
    monkeypatch.setattr(
        env, "command_output", lambda argv: {"available": False, "error": "missing binary"}
    )
    sample = env.gpu_telemetry()
    assert not sample["available"] and sample["error"] == "missing binary"
    assert all(value is None for value in sample["values"].values())


def test_quality_evaluation_identity():
    baseline = ConfigSpec()
    scheduling = ConfigSpec(prefix_caching=False, enforce_eager=True)
    with pytest.raises(ValueError):
        quality.evaluation_key(baseline, "baseline", "base", 0)
    key = quality.evaluation_key(baseline, "baseline", "base", None)
    assert quality.evaluation_key(scheduling, "candidate", "schedule", None) == key
    for spec, role, identity, limit in [
        (baseline, "combined", "combined", None),
        (baseline, "baseline", "base", 4),
        (ConfigSpec(kv_cache_dtype="fp8"), "candidate", "kv", None),
        (ConfigSpec(variant="fp8_online", quantization="fp8"), "candidate", "fp8", None),
        (ConfigSpec(seed=1), "baseline", "base", None),
    ]:
        assert quality.evaluation_key(spec, role, identity, limit) != key
    assert quality.evaluation_key(baseline, "combined", "combined", None) != quality.evaluation_key(
        scheduling, "combined", "combined", None
    )


def test_explicit_report_provenance():
    records = {
        "experiment": {"status": "completed"},
        "reps": [{"status": "ok"}, {"status": "failed"}],
    }
    assert "not run (needs GPU)" in report.evidence_scope("synthetic", records)
    assert "1 successful measured reps" in report.evidence_scope("live", records)
    assert "unverified" in report.evidence_scope("unverified", records)
    assert "no successful" in report.evidence_scope(
        "live", {"experiment": {"status": "aborted"}, "reps": []}
    )
    with pytest.raises(ValueError):
        report.evidence_scope("invented", records)
