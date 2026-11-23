"""Pure OFAT design and calibration-based cost estimates."""

import random

from inferencepilot.config import (
    VARIANTS,
    ConfigSpec,
    ExperimentPlan,
    LaunchSpec,
    PlannedConfig,
    PointSpec,
)


def changed_config(baseline, updates):
    return ConfigSpec.model_validate({**baseline.model_dump(), **updates})


def probe_for(experiment, key):
    evidence = experiment.probes.get(key)
    if evidence is None:
        return "pending", "Load probe required before live execution."
    return evidence.status, evidence.evidence


def configurations(experiment):
    baseline = experiment.baseline
    status, note = probe_for(experiment, "bf16")
    result = [
        PlannedConfig(
            label="baseline", role="baseline", spec=baseline, probe_status=status, note=note
        )
    ]
    for variant in experiment.factors.variants:
        if variant == baseline.variant:
            continue
        model, quantization = VARIANTS[variant]
        status, note = probe_for(experiment, variant)
        result.append(
            PlannedConfig(
                label=f"weights-{variant}",
                role="candidate",
                spec=changed_config(
                    baseline, {"variant": variant, "model": model, "quantization": quantization}
                ),
                probe_status=status,
                note=note,
            )
        )
    for field in (
        "prefix_caching",
        "max_num_batched_tokens",
        "max_num_seqs",
        "chunked_prefill",
        "kv_cache_dtype",
    ):
        for level in getattr(experiment.factors, field):
            if level == getattr(baseline, field):
                continue
            probe_key = {
                "chunked_prefill": "chunked_prefill_off",
                "kv_cache_dtype": "kv_cache_fp8",
            }.get(field, "bf16")
            status, note = probe_for(experiment, probe_key)
            result.append(
                PlannedConfig(
                    label=f"{field}-{str(level).lower()}",
                    role="candidate",
                    spec=changed_config(baseline, {field: level}),
                    probe_status=status,
                    note=note,
                )
            )
    result.append(
        PlannedConfig(
            label="combined",
            role="combined",
            spec=None,
            probe_status="pending_selection",
            note="Select best supported individual levels after OFAT results; validate as a new run.",
        )
    )
    status, note = probe_for(experiment, "bf16")
    result.append(
        PlannedConfig(
            label="seeded-eager",
            role="seeded_regression",
            spec=changed_config(baseline, {"enforce_eager": True}),
            probe_status=status,
            note=note,
        )
    )
    return result


def points(experiment):
    rng = random.Random(experiment.seed)
    result = []
    for workload in experiment.workloads:
        for concurrency in workload.concurrency:
            rep_seconds = experiment.calibration.rep_seconds[f"{workload.name}@{concurrency}"]
            # Calibration excludes warmups; use per-request average as a rough warmup reserve.
            seconds = experiment.reps * rep_seconds * (1 + workload.warmups / workload.num_prompts)
            result.append(
                PointSpec(
                    workload=workload.name,
                    concurrency=concurrency,
                    num_prompts=workload.num_prompts,
                    warmups=workload.warmups,
                    rep_seeds=[rng.randrange(2**32) for _ in range(experiment.reps)],
                    estimated_seconds=seconds,
                )
            )
    return result


def make_plan(experiment):
    configs = configurations(experiment)
    baseline = configs[0]
    if baseline.probe_status == "unsupported_on_hardware":
        raise ValueError("baseline probe failed; choose compatible hardware before planning")
    candidates = [
        config.label
        for config in configs
        if config.role == "candidate" and config.probe_status != "unsupported_on_hardware"
    ]
    random.Random(experiment.seed).shuffle(candidates)
    # Keep the baseline at index 0, floor(total/2), and total-1 for every factor count.
    other_labels = [*candidates, "combined", "seeded-eager"]
    middle = (len(other_labels) + 3) // 2
    labels = [
        "baseline",
        *other_labels[: middle - 1],
        "baseline",
        *other_labels[middle - 1 :],
        "baseline",
    ]
    point_specs = points(experiment)
    seconds = (
        sum(point.estimated_seconds for point in point_specs)
        + experiment.calibration.startup_seconds
        + experiment.calibration.teardown_seconds
    )
    ordinals = {}
    launches = []
    for label in labels:
        ordinals[label] = ordinals.get(label, 0) + 1
        launches.append(
            LaunchSpec(
                config_label=label,
                ordinal=ordinals[label],
                points=point_specs,
                estimated_seconds=seconds,
            )
        )
    hours = (len(launches) * seconds + experiment.calibration.extra_seconds) / 3600
    warnings = [
        "Requested flags are not resolved server settings; confirm startup logs in M3/M9.",
        "Combined configuration is deferred until OFAT results exist; its estimate uses calibration.",
        "Open-loop chat rates (50/80/95% capacity) are deferred until baseline capacity is measured; "
        "their runtime is excluded. Reserve additional budget before live execution.",
        "Warmup cost uses average request time; per-configuration runtime can differ from calibration.",
        "Pending load probes must run before live execution; failed probes remain visible in configs.",
    ]
    if experiment.calibration.source == "synthetic":
        warnings.append(
            "Synthetic calibration: demonstration estimate only, not measured GPU time."
        )
    if hours > experiment.max_gpu_hours:
        warnings.append("Estimated GPU hours exceed the configured cap; execution must enforce it.")
    return ExperimentPlan(
        experiment=experiment,
        configs=configs,
        launches=launches,
        estimated_gpu_hours=hours,
        budget_exceeded=hours > experiment.max_gpu_hours,
        warnings=warnings,
    )
