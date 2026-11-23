import hashlib

import pytest

from inferencepilot.config import ExperimentPlan, ExperimentSpec
from inferencepilot.plan_commands import plan_json
from inferencepilot.planner import make_plan


def test_deterministic_plan_and_ofat(example):
    experiment = ExperimentSpec.model_validate(example)
    first = make_plan(experiment)
    second = make_plan(experiment)
    assert (
        hashlib.sha256(plan_json(first).encode()).digest()
        == hashlib.sha256(plan_json(second).encode()).digest()
    )
    assert ExperimentPlan.model_validate_json(plan_json(first)) == first
    assert len([config for config in first.configs if config.role == "candidate"]) == 7
    assert len(first.launches) == 12
    baseline = experiment.baseline.model_dump()
    for config in first.configs:
        if config.role != "candidate":
            continue
        changed = {key for key, value in config.spec.model_dump().items() if value != baseline[key]}
        # Model identity, quantization, and variant together form one weights factor.
        if config.spec.variant != "bf16":
            assert changed <= {"model", "quantization", "variant"}
        else:
            assert len(changed) == 1
    combined = next(config for config in first.configs if config.role == "combined")
    assert combined.spec is None and combined.probe_status == "pending_selection"


@pytest.mark.parametrize("small", [True, False])
def test_schedule_baseline_positions_and_dependencies(example, small):
    if small:
        example["factors"] = {
            "variants": ["bf16"],
            "prefix_caching": [True],
            "max_num_batched_tokens": [8192],
            "max_num_seqs": [256],
        }
    plan = make_plan(ExperimentSpec.model_validate(example))
    labels = [launch.config_label for launch in plan.launches]
    assert [i for i, label in enumerate(labels) if label == "baseline"] == [
        0,
        len(labels) // 2,
        len(labels) - 1,
    ]
    assert [launch.ordinal for launch in plan.launches if launch.config_label == "baseline"] == [
        1,
        2,
        3,
    ]
    candidates = {config.label for config in plan.configs if config.role == "candidate"}
    assert all(labels.index(label) < labels.index("combined") for label in candidates)


def test_seed_changes_order_but_not_membership(example):
    first = make_plan(ExperimentSpec.model_validate(example))
    example["seed"] += 1
    second = make_plan(ExperimentSpec.model_validate(example))

    def labels(plan):
        return [launch.config_label for launch in plan.launches]

    assert labels(first) != labels(second)
    assert sorted(labels(first)) == sorted(labels(second))
    assert first.launches[0].points[0].rep_seeds != second.launches[0].points[0].rep_seeds


def test_hand_computed_estimate_and_stored_seeds(example):
    plan = make_plan(ExperimentSpec.model_validate(example))
    # 8 points, 5 reps each; chat/prefix warmup factor 1.05, rag 1.10.
    # Per-launch: 5*((120+30+15+12+15+8)*1.05+(60+24)*1.10)+180+30 = 1722.
    # 12 launches plus an explicit 600-second quality/other reserve = 21264 seconds.
    assert plan.launches[0].estimated_seconds == pytest.approx(1722)
    assert plan.estimated_gpu_hours == pytest.approx(21264 / 3600)
    for launch in plan.launches:
        assert len(launch.points) == 8
        assert all(len(point.rep_seeds) == 5 for point in launch.points)
        assert launch.points[0].rep_seeds == plan.launches[0].points[0].rep_seeds


def test_budget_and_unsupported_probe_visible(example):
    example["max_gpu_hours"] = 0.1
    example["probes"] = {
        "fp8_ckpt": {"status": "unsupported_on_hardware", "evidence": "load log tail"}
    }
    plan = make_plan(ExperimentSpec.model_validate(example))
    assert plan.budget_exceeded
    config = next(config for config in plan.configs if config.label == "weights-fp8_ckpt")
    assert config.probe_status == "unsupported_on_hardware"
    assert config.note == "load log tail"
    assert "weights-fp8_ckpt" not in [launch.config_label for launch in plan.launches]
    assert any("Open-loop" in warning for warning in plan.warnings)


def test_optional_factor_probe(example):
    example["factors"]["chunked_prefill"] = [True, False]
    example["probes"] = {
        "chunked_prefill_off": {"status": "supported", "evidence": "resolved false"}
    }
    plan = make_plan(ExperimentSpec.model_validate(example))
    assert any(config.label == "chunked_prefill-false" for config in plan.configs)


def test_failed_baseline_probe(example):
    example["probes"] = {"bf16": {"status": "unsupported_on_hardware", "evidence": "OOM"}}
    with pytest.raises(ValueError, match="baseline probe failed"):
        make_plan(ExperimentSpec.model_validate(example))
