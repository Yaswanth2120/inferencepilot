import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inferencepilot import env
from inferencepilot.config import ConfigSpec, LoadSpec, SLOSpec, WorkloadSpec
from inferencepilot.loadgen import build_command, parse_result
from inferencepilot.metrics import summarize

FAKE = Path(__file__).resolve().parents[2] / "src/inferencepilot/fakes/fake_bin/vllm"


@pytest.fixture
def fake_path(monkeypatch):
    monkeypatch.setenv(
        "PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )


@pytest.mark.parametrize("dataset", ["random", "prefix_repetition"])
@pytest.mark.parametrize("mode", ["closed", "open"])
def test_builder_fake_executable_parser_metrics(fake_path, tmp_path, dataset, mode):
    workload = WorkloadSpec(
        name="tiny",
        dataset=dataset,
        input_tokens=8,
        output_tokens=4,
        shared_prefix_tokens=16 if dataset == "prefix_repetition" else 0,
        concurrency=[2],
        num_prompts=3,
        warmups=10,
    )
    load = LoadSpec(concurrency=2) if mode == "closed" else LoadSpec(mode="open", request_rate=20)
    path = tmp_path / "rep.json"
    command = build_command(
        ConfigSpec(),
        workload,
        load,
        7,
        path,
        binary=FAKE,
        slo=SLOSpec(ttft_ms=1000, tpot_ms=1000, e2e_ms=1000),
    )
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    raw = json.loads(path.read_text())
    assert raw == json.loads(result.stdout)
    assert len(raw["ttfts"]) == workload.num_prompts  # Ten warmups are not measured requests.
    assert raw["input_lens"] == [8 + workload.shared_prefix_tokens] * 3
    assert raw["output_lens"] == [4] * 3 and "e2els" not in raw
    measured = summarize(parse_result(raw), 4)
    assert measured.status == "ok" and measured.distributions["ttft"].n == 3
    again = subprocess.run(command, capture_output=True, text=True, check=True)
    assert again.stdout == result.stdout


@pytest.mark.parametrize(
    "control", ["INFERENCEPILOT_FAKE_BENCH_FAIL_EVERY", "INFERENCEPILOT_FAKE_BENCH_TRUNCATE_EVERY"]
)
def test_fake_failed_and_truncated_reps(fake_path, tmp_path, monkeypatch, control):
    monkeypatch.setenv(control, "2")
    workload = WorkloadSpec(
        name="tiny", input_tokens=8, output_tokens=4, concurrency=[1], num_prompts=4
    )
    path = tmp_path / "partial.json"
    command = build_command(ConfigSpec(), workload, LoadSpec(concurrency=1), 7, path, binary=FAKE)
    subprocess.run(command, capture_output=True, text=True, check=True)
    measured = summarize(parse_result(json.loads(path.read_text())), 4)
    assert measured.status == "partial" and measured.completed == 2 and measured.failed == 2
    if control.endswith("FAIL_EVERY"):
        assert measured.transport_failed == 2
    else:
        assert measured.truncated == 2 and measured.transport_failed == 0


def test_fake_benchmark_process_failure(fake_path, tmp_path, monkeypatch):
    monkeypatch.setenv("INFERENCEPILOT_FAKE_BENCH_CRASH", "1")
    path = tmp_path / "missing.json"
    workload = WorkloadSpec(
        name="tiny", input_tokens=8, output_tokens=4, concurrency=[1], num_prompts=1
    )
    command = build_command(ConfigSpec(), workload, LoadSpec(concurrency=1), 0, path, binary=FAKE)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 1 and "injected benchmark failure" in result.stderr
    assert not path.exists()


def test_doctor_checks_benchmark_options_too(fake_path, monkeypatch):
    assert env.check_flags(str(FAKE)) == []
    monkeypatch.setenv("INFERENCEPILOT_FAKE_OMIT_FLAG", "--save-detailed")
    assert env.check_flags(str(FAKE)) == ["missing bench serve flag: --save-detailed"]
