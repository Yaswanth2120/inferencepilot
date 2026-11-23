"""Pure rep-level comparisons with family-wise correction and an explicit noise gate."""

import math
from collections import Counter

from inferencepilot import stats
from inferencepilot.analysis import observations


def verdict(
    effect,
    low,
    high,
    p_adjusted,
    mde,
    n_baseline,
    n_candidate,
    direction="lower_better",
    min_effect_pct=5,
):
    if direction not in ("lower_better", "higher_better"):
        raise ValueError("invalid metric direction")
    if not math.isfinite(min_effect_pct) or min_effect_pct <= 0:
        raise ValueError("min effect must be positive")
    if min(n_baseline, n_candidate) < 5 or mde is None or mde > min_effect_pct:
        return "inconclusive"
    if any(value is None for value in (effect, low, high, p_adjusted)):
        return "inconclusive"
    worse = effect if direction == "lower_better" else -effect
    if p_adjusted < 0.05 and worse >= min_effect_pct:
        return "regression"
    if p_adjusted < 0.05 and -worse >= min_effect_pct:
        return "improvement"
    if low >= -min_effect_pct and high <= min_effect_pct:
        return "no_change"
    return "inconclusive"


def compare_family(cases, min_effect_pct=5, seed=0):
    """Apply Holm once across every available point and metric for one candidate."""
    if not math.isfinite(min_effect_pct) or min_effect_pct <= 0:
        raise ValueError("min effect must be finite and positive")
    rows = []
    for index, case in enumerate(cases):
        baseline = [v for launch in case["baseline"] for v in launch]
        candidate = [v for launch in case["candidate"] for v in launch]
        row = {k: v for k, v in case.items() if k not in ("baseline", "candidate")}
        row.update(
            n_baseline=len(baseline),
            n_candidate=len(candidate),
            effect_pct=None,
            ci_low=None,
            ci_high=None,
            p_value=None,
            mde_pct=None,
        )
        try:
            center = stats.mean(baseline)
            if center <= 0:
                raise ValueError("percent effect needs positive baseline mean")
            low, high = stats.bootstrap_effect_ci(baseline, candidate, seed=seed + index)
            mde = stats.minimum_detectable_effect(
                case["baseline"],
                candidate_reps_per_launch=min(map(len, case["candidate"])),
                candidate_launches=len(case["candidate"]),
            )
            row.update(
                effect_pct=100 * (stats.mean(candidate) / center - 1),
                ci_low=low,
                ci_high=high,
                p_value=stats.permutation_test(baseline, candidate, seed=seed + index).p_value,
                mde_pct=mde.mde_pct,
            )
        except ValueError:
            pass
        rows.append(row)
    adjusted = (
        stats.holm_adjust([r["p_value"] if r["p_value"] is not None else 1 for r in rows])
        if rows
        else []
    )
    for row, p in zip(rows, adjusted):
        row["p_adjusted"] = p
        row["verdict"] = verdict(
            row["effect_pct"],
            row["ci_low"],
            row["ci_high"],
            p,
            row["mde_pct"],
            row["n_baseline"],
            row["n_candidate"],
            row["direction"],
            min_effect_pct,
        )
    return rows


def cases_for(grouped, baseline_id, candidate_id):
    keys = {
        (point, metric)
        for config, point, metric in grouped
        if config in (baseline_id, candidate_id)
    }
    return [
        dict(
            point_key=point,
            workload=point.split(":")[0],
            metric=metric,
            direction="higher_better" if "throughput" in metric else "lower_better",
            baseline=list(grouped.get((baseline_id, point, metric), {}).values()),
            candidate=list(grouped.get((candidate_id, point, metric), {}).values()),
        )
        for point, metric in sorted(keys)
    ]


def compare_experiment(records, baseline_label="baseline", min_effect_pct=5):
    grouped = observations(records)
    baseline = next(c for c in records["configs"] if c["label"] == baseline_label)
    results = []
    for candidate in records["configs"]:
        if candidate["id"] == baseline["id"]:
            continue
        rows = compare_family(
            cases_for(grouped, baseline["id"], candidate["id"]),
            min_effect_pct,
            seed=records["experiment"]["seed"],
        )
        for row in rows:
            row.update(baseline_config_id=baseline["id"], candidate_config_id=candidate["id"])
        results.extend(rows)
    return results


def summary(rows):
    counts = dict(Counter(row["verdict"] for row in rows))
    worst = next(
        (v for v in ("regression", "inconclusive", "no_change", "improvement") if counts.get(v)),
        "inconclusive",
    )
    return {"verdict": worst, "counts": counts, "n_tests": len(rows)}


def validate(records):
    """Leave out every physical baseline launch once; count both false directional findings."""
    grouped = observations(records)
    baseline_id = next(c["id"] for c in records["configs"] if c["role"] == "baseline")
    launch_ids = sorted(
        {
            launch
            for (config, _, _), launches in grouped.items()
            if config == baseline_id
            for launch in launches
        }
    )
    rows = []
    for held_out in launch_ids:
        cases = []
        for (config, point, metric), launches in sorted(grouped.items()):
            if config != baseline_id:
                continue
            cases.append(
                dict(
                    point_key=point,
                    metric=metric,
                    direction="higher_better" if "throughput" in metric else "lower_better",
                    baseline=[reps for launch, reps in launches.items() if launch != held_out],
                    candidate=[launches[held_out]] if held_out in launches else [],
                )
            )
        rows.extend(compare_family(cases, seed=records["experiment"]["seed"]))
    false_positives = sum(r["verdict"] in ("regression", "improvement") for r in rows)
    n = len(rows)
    return {
        "n_tests": n,
        "false_positives": false_positives,
        "false_positive_rate": false_positives / n if n else None,
        "inconclusive": sum(r["verdict"] == "inconclusive" for r in rows),
        "baseline_launches": len(launch_ids),
        "tests": rows,
        "note": "Overlapping leave-one-launch splits are correlated; rate is descriptive, not independent trials.",
    }
