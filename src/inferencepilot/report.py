"""Render persisted evidence without alternate statistical formulas."""

import json
import math
import time
from pathlib import Path

from inferencepilot import analysis, regress
from inferencepilot.recommend import Constraints, recommend
from inferencepilot.store import encode


def evidence_scope(kind, records):
    """Describe declared measurement origin without inferring live execution from a GPU name."""
    if kind == "synthetic":
        return "synthetic offline measurements; live model paths: not run (needs GPU)"
    if kind == "live":
        valid = sum(rep["status"] == "ok" for rep in records["reps"])
        if not valid:
            return "live campaign declared; no successful measured reps captured"
        return f"live measurements declared; {valid} successful measured reps; campaign status={records['experiment']['status']}"
    if kind == "unverified":
        return "measurement provenance unverified; no live execution claim"
    raise ValueError("unknown measurement provenance")


def prepare(store, experiment, constraints):
    records = store.records(experiment)
    saved = store.meta("evidence:" + experiment)
    evidence = (
        json.loads(saved)
        if saved
        else {"kind": "unverified", "basis": "legacy database; provenance not recorded"}
    )
    scope = evidence_scope(evidence["kind"], records)
    constraints = Constraints.model_validate(constraints)
    aggregates = analysis.aggregate(records)
    comparisons = regress.compare_experiment(records)
    store.replace_regressions(experiment, comparisons)
    validation = regress.validate(records)
    store.set_meta("validation:" + experiment, encode(validation))
    candidates = analysis.recommendation_inputs(
        records, aggregates, comparisons, constraints.quality.filter
    )
    decision = recommend(candidates, constraints)
    store.insert(
        "recommendations",
        experiment_id=experiment,
        constraints=encode(constraints.model_dump()),
        ranking=encode(decision),
        chosen_config_id=decision["chosen_config_id"],
        created_at=time.time(),
    )
    return dict(
        schema_version=1,
        experiment=records["experiment"],
        environment=json.loads(
            store.rows("env_snapshots", id=records["experiment"]["env_id"])[0]["data"]
        ),
        records=records,
        aggregates=aggregates,
        regressions=comparisons,
        validation=validation,
        recommendation=decision,
        evidence=evidence,
        live=scope,
        measurement_notes=[
            "Latency values are mean-of-rep percentiles in ms; intervals resample reps (10000 draws).",
            "Quality rows marked inherited reuse the named original evaluation; they are not new GSM8K measurements. Combined candidates require their own evaluation.",
            "E2E is reconstructed from TTFT plus streaming gaps. Parser and fake fixtures remain provisional.",
            "Inconclusive comparisons and MDE accompany ranking; no statistical superiority is inferred from rank.",
        ],
    )


def number(value, n):
    """Refuse measurement formatting without an explicit positive observation count."""
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ValueError("a rate or percentile requires its positive n")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("measurement must be finite")
    return f"{value:.6g} (n={n})"


def markdown(bundle):
    records = bundle["records"]
    labels = {c["id"]: c["label"] for c in records["configs"]}
    launches = {launch["id"]: launch for launch in records["launches"]}
    lines = [
        "# InferencePilot experiment report",
        "",
        bundle["experiment"]["name"],
        "",
        "**Evidence scope:** "
        + bundle["live"]
        + ". Synthetic experiments are demonstrations only.",
        "",
        "## Environment",
        "",
        "```json",
        json.dumps(bundle["environment"], indent=2),
        "```",
        "",
        "## Requested and resolved configurations",
        "",
        "| Label / role | Requested | Actual launch / status / resolved |",
        "|---|---|---|",
    ]
    for config in records["configs"]:
        actual = [
            {k: launch[k] for k in ("id", "status", "resolved_args", "error", "log_path")}
            for launch in records["launches"]
            if launch["config_id"] == config["id"]
        ]
        lines.append(
            f"| {config['label']} / {config['role']} | `{config['spec']}` | `{encode(actual)}` |"
        )
    lines.extend(
        [
            "",
            "## Per-workload metrics",
            "",
            "Mean of rep statistics; 95% bootstrap CI. n is the number of reps, not independent requests.",
            "",
            "| Config | Workload / mode / load | Metric | Mean (n reps) | CI low / high | Launches |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in bundle["aggregates"]:
        n = row["n_reps"]
        lines.append(
            f"| {labels[row['config_id']]} | {row['point']} | {row['metric']} | {number(row['mean'], n)} | {number(row['ci_low'], n)} / {number(row['ci_high'], n)} | {row['n_launches']} |"
        )
    excluded = [
        dict(id=r["id"], status=r["status"], summary=json.loads(r["summary"]))
        for r in records["reps"]
        if r["status"] != "ok"
    ]
    lines.extend(
        [
            "",
            "Excluded reps: `" + encode(excluded) + "`",
            "",
            "## Regression evidence",
            "",
            "| Candidate | Point | Metric | Effect % / CI % | Adjusted p | MDE % | Baseline / candidate reps | Verdict |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in bundle["regressions"]:
        lines.append(
            f"| {labels[row['candidate_config_id']]} | {row['point_key']} | {row['metric']} | {row['effect_pct']} / [{row['ci_low']}, {row['ci_high']}] | {row['p_adjusted']} | {row['mde_pct']} | {row['n_baseline']} / {row['n_candidate']} | {row['verdict']} |"
        )
    aa = bundle["validation"]
    lines.extend(
        [
            "",
            f"A/A false directional findings: {aa['false_positives']}/{aa['n_tests']}; inconclusive: {aa['inconclusive']}. Splits overlap.",
            "",
            "## Quality and McNemar",
            "",
            "Inherited rows reuse their named source evaluation; do not sum them as independent samples.",
            "",
            "| Config / launch | Task | n source problems | Evidence (accuracy CI and paired McNemar) |",
            "|---|---|---|---|",
        ]
    )
    for row in records["quality"]:
        lines.append(
            f"| {labels[launches[row['launch_id']]['config_id']]} / {row['launch_id']} | {row['task']} | {row['n']} | `{row['metrics']}` |"
        )
    lines.extend(
        [
            "",
            "## Greedy token agreement",
            "",
            "| Config | Exact match rate (n prompts) | Mean first divergent token position |",
            "|---|---|---|",
        ]
    )
    for row in records["agreement"]:
        lines.append(
            f"| {labels[launches[row['launch_id']]['config_id']]} | {number(row['exact_match_rate'], row['n'])} | {row['mean_first_divergence']} |"
        )
    lines.extend(
        [
            "",
            "Position is zero-based; matching outputs are excluded, strict prefixes diverge at the shorter length.",
            "",
            "## Recommendation",
            "",
            bundle["recommendation"]["description"],
            "",
            "```json",
            json.dumps(bundle["recommendation"], indent=2),
            "```",
            "",
            "## Measurement limitations",
            "",
            *bundle["measurement_notes"],
            "",
            "OFAT does not explore all interactions. Combined candidates require their own measured validation. Evidence: "
            + bundle["live"]
            + ".",
            "",
        ]
    )
    return "\n".join(lines)


def plots(bundle, directory):
    """Optionally draw count-labelled throughput and p95 E2E evidence using matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    labels = {c["id"]: c["label"] for c in bundle["records"]["configs"]}
    paths = []
    for metric in ("output_throughput", "p95_e2e"):
        rows = [
            r
            for r in bundle["aggregates"]
            if r["metric"] == metric
            and r["point"] == bundle["recommendation"]["constraints"]["objective"]["point"]
        ]
        if not rows:
            continue
        for row in rows:
            number(row["mean"], row["n_reps"])
        figure, axis = plt.subplots(figsize=(max(10, len(rows) * 1.8), 6))
        positions = list(range(len(rows)))
        axis.errorbar(
            positions,
            [r["mean"] for r in rows],
            yerr=[
                [r["mean"] - r["ci_low"] for r in rows],
                [r["ci_high"] - r["mean"] for r in rows],
            ],
            fmt="o",
            capsize=4,
        )
        axis.set_xticks(
            positions,
            [f"{labels[r['config_id']]}\nn={r['n_reps']} reps" for r in rows],
            rotation=25,
            ha="right",
        )
        axis.set_ylabel("tokens/s" if metric == "output_throughput" else "mean rep p95 E2E (ms)")
        scope = bundle.get("evidence", {}).get("kind", "unverified")
        axis.set_title(bundle["experiment"]["name"] + " — " + metric + f" (95% CI; {scope})")
        axis.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        path = directory / (metric + ".png")
        figure.savefig(path, dpi=150)
        plt.close(figure)
        paths.append(path.name)
    return paths


def write(bundle, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rendered = markdown(bundle)  # Validate count-bearing measurements before writing anything.
    images = plots(bundle, directory)
    if images:
        rendered += "\n## Plots\n\n" + "\n\n".join(f"![{name}]({name})" for name in images) + "\n"
    (directory / "report.json").write_text(encode(bundle) + "\n")
    (directory / "report.md").write_text(rendered)
    return ["report.md", "report.json", *images]
