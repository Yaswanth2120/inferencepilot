import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from inferencepilot.config import ConfigSpec, ExperimentSpec, LoadSpec, SLOSpec
from inferencepilot.loadgen import AdapterBrokenError, build_command, parse_result

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/provisional"


@pytest.fixture
def worked_raw():
    return json.loads((FIXTURES / "bench_worked.json").read_text())


def test_exact_workload_point_commands(example):
    experiment = ExperimentSpec.model_validate(example)
    snapshots = json.loads((FIXTURES / "bench_commands.json").read_text())
    checked = set()
    for workload in experiment.workloads:
        for concurrency in workload.concurrency:
            key = f"{workload.name}@closed:{concurrency}"
            command = build_command(
                experiment.baseline,
                workload,
                LoadSpec(concurrency=concurrency),
                17,
                "data/raw/rep.json",
            )
            assert command == snapshots[key]
            checked.add(key)
        if workload.name == "chat":
            for rate in (10.0, 16.0, 19.0):
                key = f"chat@open:{rate}"
                command = build_command(
                    experiment.baseline,
                    workload,
                    LoadSpec(mode="open", request_rate=rate),
                    17,
                    "data/raw/rep.json",
                )
                assert command == snapshots[key]
                assert "--max-concurrency" not in command
                checked.add(key)
    assert checked == set(snapshots) and len(checked) == 11


def test_slo_arguments_and_custom_binary(example):
    experiment = ExperimentSpec.model_validate(example)
    command = build_command(
        experiment.baseline,
        experiment.workloads[0],
        LoadSpec(concurrency=1),
        0,
        "rep.json",
        binary="/fake/vllm",
        slo=SLOSpec(ttft_ms=100, tpot_ms=20, e2e_ms=500),
    )
    assert command[0] == "/fake/vllm"
    assert command[-4:] == ["--goodput", "ttft:100.0", "tpot:20.0", "e2el:500.0"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"concurrency": True},
        {"concurrency": "1"},
        {"concurrency": 0},
        {"concurrency": 1, "request_rate": 2},
        {"mode": "open", "concurrency": 1},
        {"mode": "open", "request_rate": float("inf")},
        {"mode": "open", "request_rate": 0},
    ],
)
def test_invalid_load(kwargs):
    with pytest.raises(ValidationError):
        LoadSpec(**kwargs)


def test_invalid_command_inputs(example):
    experiment = ExperimentSpec.model_validate(example)
    workload = experiment.workloads[0]
    for seed in (-1, True, 2**32):
        with pytest.raises(ValueError, match="seed"):
            build_command(experiment.baseline, workload, LoadSpec(concurrency=1), seed, "rep.json")
    with pytest.raises(ValueError, match="JSON"):
        build_command(experiment.baseline, workload, LoadSpec(concurrency=1), 0, "rep.txt")
    with pytest.raises(ValueError, match="configured workload point"):
        build_command(experiment.baseline, workload, LoadSpec(concurrency=2), 0, "rep.json")
    with pytest.raises(ValueError, match="exceeds"):
        build_command(
            ConfigSpec(max_model_len=256), workload, LoadSpec(concurrency=1), 0, "rep.json"
        )


def test_parse_schema_and_bundled_stream_gaps(worked_raw):
    parsed = parse_result(worked_raw)
    assert parsed.duration_s == 2 and len(parsed.requests) == 3
    assert all(request.success for request in parsed.requests)
    assert [len(request.gaps_s) for request in parsed.requests] == [2, 1, 1]
    assert parsed.requests[1].output_tokens == 3  # One gap can span multiple output tokens.
    assert parsed.tool_summary["p99_e2el_ms"] == 500
    assert parsed.parser_status == "provisional"
    before = copy.deepcopy(worked_raw)
    parse_result(worked_raw)
    assert worked_raw == before


@pytest.mark.parametrize(
    "change",
    [
        "missing_details",
        "length",
        "counts",
        "negative_gap",
        "nan",
        "string_number",
        "bool_count",
        "failed_tokens",
        "backend",
        "missing_p99",
        "zero_duration",
    ],
)
def test_invalid_result_is_adapter_broken(worked_raw, change):
    if change == "missing_details":
        worked_raw.pop("itls")
    elif change == "length":
        worked_raw["errors"].pop()
    elif change == "counts":
        worked_raw["completed"] = 2
    elif change == "negative_gap":
        worked_raw["itls"][0] = [-1]
    elif change == "nan":
        worked_raw["ttfts"][0] = float("nan")
    elif change == "string_number":
        worked_raw["ttfts"][0] = "0.1"
    elif change == "bool_count":
        worked_raw["completed"] = True
    elif change == "failed_tokens":
        worked_raw["errors"][0] = "failed"
        worked_raw["completed"] = 2
        worked_raw["failed"] = 1
    elif change == "backend":
        worked_raw["backend"] = "openai-chat"
    elif change == "missing_p99":
        worked_raw.pop("p99_e2el_ms")
    elif change == "zero_duration":
        worked_raw["duration"] = 0
    with pytest.raises(AdapterBrokenError, match="adapter broken"):
        parse_result(worked_raw)


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "100"])
def test_invalid_slo_thresholds(value):
    with pytest.raises(ValidationError):
        SLOSpec(ttft_ms=value, tpot_ms=100, e2e_ms=1000)


def test_existing_endpoint_preserves_qwen_launch_validation(tmp_path):
    from inferencepilot.config import BenchmarkEndpoint, ConfigSpec, LoadSpec, WorkloadSpec

    endpoint = BenchmarkEndpoint(model="openai/gpt-oss-120b", port=18000, max_model_len=8192)
    workload = WorkloadSpec(
        name="chat",
        dataset="random",
        input_tokens=256,
        output_tokens=256,
        concurrency=[1],
        num_prompts=100,
    )
    command = build_command(endpoint, workload, LoadSpec(concurrency=1), 42, tmp_path / "real.json")
    assert command[command.index("--model") + 1] == "openai/gpt-oss-120b"
    assert command[command.index("--port") + 1] == "18000"
    with pytest.raises(ValueError):
        ConfigSpec(model="openai/gpt-oss-120b")
    with pytest.raises(ValueError):
        BenchmarkEndpoint(
            model="openai/gpt-oss-120b", port=18000, max_model_len=8192, enforce_eager=True
        )
