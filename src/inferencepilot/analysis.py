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
    chosen = {}
    for identity, values in scores.items():
        config = configs[identity]
        if config["role"] != "candidate" or max(values) <= reference:
            continue
        spec = json.loads(config["spec"])
        for key, value in spec.items():
            if (
                value != baseline.model_dump()[key]
                and max(values) > chosen.get(key, (reference, None))[0]
            ):
                chosen[key] = (max(values), value)
    return ConfigSpec.model_validate(
        {**baseline.model_dump(), **{k: v[1] for k, v in chosen.items()}}
    )
