import json
from pathlib import Path

import pytest

from inferencepilot.loadgen import parse_result
from inferencepilot.metrics import summarize


def test_real_gptoss_smoke_metrics():
    raw = json.loads(
        (Path(__file__).parents[1] / "fixtures/real/gptoss_vllm_032_smoke.json").read_text()
    )
    result = summarize(parse_result(raw), 4)
    assert result.status == "ok"
    assert result.attempted == result.completed == 3
    assert result.output_throughput.total == 12
    # Direct API latency is now present; confirm the reconstruction on this real sample.
    assert result.distributions["e2e"].mean == pytest.approx(sum(raw["latencies"]) / 3 * 1000)
    assert result.request_throughput.value == pytest.approx(3 / raw["duration"])
