"""Check presentation against changed evidence, not just the published winner."""

import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_figures_follow_changed_recommendation_and_replication(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    namespace = runpy.run_path(str(ROOT / "scripts/readme_figures.py"))
    plt = namespace["plt"]
    data = json.loads((ROOT / "reports/qwen3-20261125/report.json").read_text())
    data = copy.deepcopy(data)
    configs = {c["label"]: c["id"] for c in data["records"]["configs"]}
    data["recommendation"]["chosen_config_id"] = configs["weights-fp8_online"]
    data["recommendation"]["constraints"]["points"]["chat:closed:32"]["p95_ttft"] = 1000
    for row in data["aggregates"]:
        row["n_reps"] = 21 if row["config_id"] == configs["baseline"] else 7
        row["n_launches"] = 4 if row["config_id"] == configs["baseline"] else 2
    original_close = plt.close
    monkeypatch.setattr(plt, "close", lambda *args: None)
    try:
        namespace["plot_qwen_performance"](data, tmp_path / "performance.png")
        fig = plt.gcf()
        caption = " ".join(t.get_text() for t in fig.texts)
        assert "21 reps / 4 launches" in caption and "7 reps / 2 launches" in caption
        assert "does not overlap 1000 ms" in caption
        axis = fig.axes[0]
        green = [line for line in axis.lines if line.get_color() == "#0f766e"]
        expected = next(
            r["mean"]
            for r in data["aggregates"]
            if r["config_id"] == configs["weights-fp8_online"]
            and r["metric"] == "output_throughput"
            and r["point"] == "chat:closed:32"
        )
        assert any(list(line.get_xdata()) == [expected] for line in green)
        assert any(line.get_label() == "1000 ms SLO" for line in fig.axes[1].lines)
        namespace["plot_qwen_regressions"](data, tmp_path / "regressions.png")
        assert "weights-awq" not in [t.get_text() for t in plt.gcf().axes[0].get_yticklabels()]
        assert "7 reps / 2 launches" in " ".join(t.get_text() for t in plt.gcf().texts)
        data["recommendation"]["chosen_config_id"] = None
        namespace["plot_qwen_performance"](data, tmp_path / "none.png")
        assert "No configuration satisfies" in " ".join(t.get_text() for t in plt.gcf().texts)
        assert not any(line.get_color() == "#0f766e" for line in plt.gcf().axes[0].lines)
    finally:
        original_close("all")


def test_campaign_hash_manifest_and_agreement_launches():
    import hashlib

    from inferencepilot.report import markdown

    directory = ROOT / "reports/qwen3-20261125"
    manifest = json.loads((directory / "verification.json").read_text())
    expected = {str(p.relative_to(ROOT)) for p in directory.glob("*.png")}
    expected |= {str(p.relative_to(ROOT)) for p in (ROOT / "reports/readme").glob("*.png")}
    expected |= {"reports/qwen3-20261125/report.md", "reports/qwen3-20261125/report.json"}
    assert expected <= manifest["public_artifact_sha256"].keys()
    assert (
        manifest["public_report_sha256"]
        == manifest["public_artifact_sha256"]["reports/qwen3-20261125/report.json"]
    )
    for name, digest in manifest["public_artifact_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    data = json.loads((directory / "report.json").read_text())
    text = markdown(data)
    for row in data["records"]["agreement"]:
        assert f"/ {row['launch_id']} (reference {row['reference_launch_id']})" in text
