"""Rep-level aggregation shared by orchestration and reporting."""

import json

from inferencepilot import stats
from inferencepilot.config import ConfigSpec


def point_key(point):
    return f"{point['workload']}:{point['mode']}:{point['concurrency'] if point['mode'] == 'closed' else point['request_rate']}"


def observations(records):
    launches = {r["id"]: r for r in records["launches"]}
    points = {r["id"]: r for r in records["points"]}
    grouped = {}
    for rep in records["reps"]:
        if rep["status"] != "ok":
            continue
        point = points[rep["point_id"]]
        launch = launches[point["launch_id"]]
        summary = json.loads(rep["summary"])
        values = {
            name: summary[name]["value"] for name in ("request_throughput", "output_throughput")
        }
        if summary.get("goodput") is not None:
            values["goodput"] = summary["goodput"]["value"]
        values.update(
            {
                f"p95_{name}": d["p95"]
                for name, d in summary["distributions"].items()
                if d["p95"] is not None
            }
        )
        for metric, value in values.items():
            key = (launch["config_id"], point_key(point), metric)
            grouped.setdefault(key, {}).setdefault(launch["id"], []).append(value)
    return grouped


def aggregate(records):
    result = []
    for (config, point, metric), launches in observations(records).items():
        values = [value for reps in launches.values() for value in reps]
        low, high = stats.bootstrap_ci(values)
        result.append(
            dict(
                config_id=config,
                point=point,
                metric=metric,
                mean=stats.mean(values),
                ci_low=low,
                ci_high=high,
                n_reps=len(values),
                n_launches=len(launches),
            )
        )
    return result


def capacity(records, baseline_id):
    rates = []
    for (config, point, metric), launches in observations(records).items():
        if (
            config == baseline_id
            and point.startswith("chat:closed:")
            and metric == "request_throughput"
        ):
            values = [v for reps in launches.values() for v in reps]
            rates.append((stats.mean(values), len(values)))
    if not rates:
        return None
    rate, n = max(rates)
    return {"requests_per_second": rate, "n_reps": n, "fractions": [0.5, 0.8, 0.95]}


def combined_spec(records, baseline):
    """Choose each observed OFAT level independently; validate interactions in its own launch."""
    grouped = observations(records)
    configs = {c["id"]: c for c in records["configs"]}
    scores = {}
    for (identity, point, metric), launches in grouped.items():
        if point.startswith("chat:closed:") and metric == "output_throughput":
            scores.setdefault(identity, []).append(
                stats.mean([v for reps in launches.values() for v in reps])
            )
    baseline_id = next(c["id"] for c in records["configs"] if c["role"] == "baseline")
    reference = max(scores.get(baseline_id, [float("inf")]))
    weight_fields = ("variant", "model", "quantization")
    weights = {key: baseline.model_dump()[key] for key in weight_fields}
    weight_score = reference
    chosen = {}
    for identity, values in scores.items():
        config = configs[identity]
        if config["role"] != "candidate" or max(values) <= reference:
            continue
        spec = json.loads(config["spec"])
        if max(values) > weight_score and any(
            spec[key] != baseline.model_dump()[key] for key in weight_fields
        ):
            weights = {key: spec[key] for key in weight_fields}
            weight_score = max(values)
        for key, value in spec.items():
            if (
                key not in weight_fields
                and value != baseline.model_dump()[key]
                and max(values) > chosen.get(key, (reference, None))[0]
            ):
                chosen[key] = (max(values), value)
    return ConfigSpec.model_validate(
        {**baseline.model_dump(), **weights, **{k: v[1] for k, v in chosen.items()}}
    )


def recommendation_inputs(records, aggregates, regressions, quality_filter="flexible-extract"):
    """Join precomputed metrics and paired quality without repeating statistical calculations."""
    result = []
    for config in records["configs"]:
        points = {}
        for row in aggregates:
            if row["config_id"] == config["id"]:
                points.setdefault(row["point"], {})[row["metric"]] = row
        launches = sorted(
            [
                launch
                for launch in records["launches"]
                if launch["config_id"] == config["id"] and launch["status"] == "ok"
            ],
            key=lambda launch: launch["started_at"],
        )
        latest = launches[-1]["id"] if launches else None
        samples = [
            q for q in records["quality"] if q["launch_id"] == latest and q["task"] == "gsm8k"
        ]
        quality = None
        if samples:
            metrics = json.loads(samples[-1]["metrics"])
            if metrics.get("status") == "ok":
                accuracy = metrics["filters"][quality_filter]
                paired = metrics.get("paired", {}).get(quality_filter)
                if config["role"] == "baseline":
                    paired = {"n": accuracy["n"], "drop_percentage_points": 0, "mcnemar_p": 1}
                if paired:
                    quality = dict(
                        accuracy=accuracy["accuracy"],
                        n=paired["n"],
                        drop_pp=paired["drop_percentage_points"],
                        mcnemar_p=paired["mcnemar_p"],
                        source={
                            "inherited": metrics.get("inherited", False),
                            "quality_id": metrics.get("source_quality_id", samples[-1]["id"]),
                            "launch_id": metrics.get("source_launch_id", samples[-1]["launch_id"]),
                        },
                    )
        relevant = [r for r in regressions if r["candidate_config_id"] == config["id"]]
        warnings = [
            dict(
                point=r["point_key"],
                metric=r["metric"],
                verdict=r["verdict"],
                mde_pct=r["mde_pct"],
                n_baseline=r["n_baseline"],
                n_candidate=r["n_candidate"],
            )
            for r in relevant
        ]
        errors = []
        if not launches:
            errors.append(
                "No successful measured server launch; unsupported, failed, or untested configuration"
            )
        if any(
            not json.loads(launch["resolved_args"]).get("raw_matched_lines") for launch in launches
        ):
            errors.append("Resolved settings missing from startup evidence")
        result.append(
            dict(
                id=config["id"],
                label=config["label"],
                role=config["role"],
                points=points,
                quality=quality,
                warnings=warnings,
                errors=errors,
            )
        )
    return result
