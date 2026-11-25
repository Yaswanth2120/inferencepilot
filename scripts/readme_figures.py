#!/usr/bin/env python3
"""Render README figures from published summaries and a dated progress snapshot."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def plot_results(source, destination):
    """Display saved GPT-OSS means and intervals without recomputing statistics."""
    data = json.loads(source.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for axis, metric, scale, title, unit in (
        (axes[0], "output_throughput", 1, "Output throughput", "Output tokens / second"),
        (
            axes[1],
            "p95_e2e",
            1000,
            "Latency under client concurrency",
            "Mean rep p95 E2E (seconds)",
        ),
    ):
        for workload, color in (("chat", "#2563eb"), ("rag", "#c2410c")):
            rows = [
                row
                for row in data["metrics"]
                if row["metric"] == metric and row["point"].startswith(workload + ":")
            ]
            rows.sort(key=lambda row: int(row["point"].split(":")[-1]))
            if len(rows) != 3 or any(row["n_reps"] != 5 or row["n_launches"] != 1 for row in rows):
                raise ValueError("expected three points with five reps in one server lifetime")
            means = [row["mean"] / scale for row in rows]
            errors = [
                [(row["mean"] - row["ci_low"]) / scale for row in rows],
                [(row["ci_high"] - row["mean"]) / scale for row in rows],
            ]
            axis.errorbar(
                range(3),
                means,
                yerr=errors,
                label=workload,
                color=color,
                marker="o",
                linewidth=2,
                capsize=5,
            )
        axis.set(
            title=title,
            xlabel="Client concurrency",
            ylabel=unit,
            xticks=range(3),
            xticklabels=["1", "8", "32"],
        )
        axis.set_ylim(bottom=0)
        axis.grid(axis="y", alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
        axis.legend(frameon=False)
    fig.suptitle(
        "Measured GPT-OSS-120B results · single A100 80 GB", fontsize=15, fontweight="bold"
    )
    fig.text(
        0.5,
        0.03,
        "5 reps × 100 requests per point · 95% bootstrap CIs (some narrower than markers)\nOne server lifetime · max_num_seqs=1: higher client concurrency measures queueing",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.12, 1, 0.92))
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def plot_progress(source, destination):
    """Show observed campaign counts with their snapshot time and explicit denominators."""
    data = json.loads(source.read_text())
    stamp = datetime.fromtimestamp(data["snapshot_unix"], ZoneInfo("America/New_York"))
    fig, axis = plt.subplots(figsize=(11, 3.8))
    for y, count, total, color in (
        (1, data["valid_reps"], data["planned_reps"], "#2563eb"),
        (0, data["finished_launches"], data["planned_launches"], "#0f766e"),
    ):
        if total <= 0 or not 0 <= count <= total:
            raise ValueError("progress needs a valid count and positive denominator")
        fraction = count / total
        axis.barh(y, 1, height=0.35, color="#e2e8f0")
        axis.barh(y, fraction, height=0.35, color=color)
        axis.text(1.02, y, f"{count:,} / {total:,}  ({fraction:.0%})", va="center", fontsize=11)
    axis.set(
        yticks=[1, 0],
        yticklabels=["Valid benchmark reps", "Completed launches"],
        xlim=(0, 1.35),
        ylim=(-0.6, 1.6),
    )
    axis.tick_params(axis="both", length=0)
    axis.set_xticks([])
    axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
    fig.suptitle(
        "Qwen3-8B campaign · "
        + ("completed" if data["phase"] == "completed" else "work in progress"),
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.80,
        f"Snapshot: {stamp:%Y-%m-%d %H:%M %Z} · {data['failed_reps']} failed/partial reps · {data['elapsed_hours']:.1f} h elapsed / {data['cap_hours']} h cap",
        ha="center",
        fontsize=10,
        color="#475569",
    )
    fig.text(
        0.5,
        0.06,
        "Measurements and automated analysis completed; final report archived."
        if data["phase"] == "completed"
        else "Count-based progress, not a completion-time estimate. Final comparisons and recommendation are pending.",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0.02, 0.13, 0.98, 0.83))
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def replication_caption(data):
    """Describe observed rep/launch counts without assuming equal candidate replication."""
    baseline = {c["id"] for c in data["records"]["configs"] if c["role"] == "baseline"}
    parts = []
    for name, is_baseline in (("Baseline", True), ("Candidates", False)):
        counts = sorted(
            {
                (row["n_reps"], row["n_launches"])
                for row in data["aggregates"]
                if (row["config_id"] in baseline) == is_baseline
            }
        )
        sizes = ", ".join(f"{reps} reps / {launches} launches" for reps, launches in counts)
        parts.append(f"{name}: {sizes or 'no measured aggregates'}")
    return "; ".join(parts)


def plot_qwen_performance(data, destination):
    """Plot saved objective-point means and CIs alongside its saved TTFT constraint."""
    labels = {c["id"]: c["label"] for c in data["records"]["configs"]}
    recommendation = data["recommendation"]
    chosen = recommendation["chosen_config_id"]
    point = recommendation["constraints"]["objective"]["point"]
    threshold = recommendation["constraints"]["points"].get(point, {}).get("p95_ttft")
    measured = {
        r["config_id"]
        for r in data["aggregates"]
        if r["point"] == point and r["metric"] == "output_throughput"
    }
    order = [c["label"] for c in data["records"]["configs"] if c["id"] in measured]
    short = order
    if chosen is not None and chosen not in measured:
        raise ValueError("chosen configuration lacks objective-point measurements")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for axis, metric, title, unit in (
        (axes[0], "output_throughput", "Output throughput", "Output tokens / second"),
        (axes[1], "p95_ttft", "Time to first token", "Mean rep p95 TTFT (ms)"),
    ):
        rows = {
            labels[r["config_id"]]: r
            for r in data["aggregates"]
            if r["point"] == point and r["metric"] == metric
        }
        for y, label in enumerate(order):
            row = rows[label]
            if row["n_reps"] < 5:
                raise ValueError("Qwen plot requires at least five comparable reps")
            color = (
                "#0f766e"
                if row["config_id"] == chosen
                else "#c2410c"
                if label == "seeded-eager"
                else "#2563eb"
            )
            axis.errorbar(
                row["mean"],
                y,
                xerr=[[row["mean"] - row["ci_low"]], [row["ci_high"] - row["mean"]]],
                fmt="o",
                color=color,
                capsize=4,
                markersize=7,
            )
        axis.set(
            title=title, xlabel=unit, yticks=range(len(order)), yticklabels=short, xlim=(0, None)
        )
        axis.grid(axis="x", alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].invert_yaxis()
    if threshold is not None:
        axes[1].axvline(
            threshold, color="#c2410c", linestyle="--", alpha=0.7, label=f"{threshold:g} ms SLO"
        )
        axes[1].legend(frameon=False, loc="lower right")
    chosen_rows = [
        r
        for r in data["aggregates"]
        if r["config_id"] == chosen and r["point"] == point and r["metric"] == "p95_ttft"
    ]
    note = "No configuration satisfies the saved constraints."
    if chosen is not None:
        note = "Green: best tested configuration under mean-of-rep SLO policy."
        if threshold is not None and chosen_rows:
            row = chosen_rows[0]
            relation = (
                "overlaps" if row["ci_low"] <= threshold <= row["ci_high"] else "does not overlap"
            )
            note += f" Its TTFT CI {relation} {threshold:g} ms."
    fig.suptitle(
        f"Qwen3-8B · measured capacity and latency at {point}",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.025,
        f"95% rep-bootstrap CIs · {replication_caption(data)}\n{note}",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.10, 1, 0.94))
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def plot_qwen_quality(data, destination):
    """Show independent measured quality evaluations without counting inherited rows twice."""
    launches = {r["id"]: r["config_id"] for r in data["records"]["launches"]}
    labels = {r["id"]: r["label"] for r in data["records"]["configs"]}
    measured = {}
    for row in data["records"]["quality"]:
        metrics = json.loads(row["metrics"])
        if metrics.get("status") == "ok" and not metrics.get("inherited"):
            measured[labels[launches[row["launch_id"]]]] = metrics
    fig, axis = plt.subplots(figsize=(11, 4.5))
    names = ["baseline", "weights-fp8_online", "weights-fp8_ckpt", "combined"]
    display = ["BF16 baseline", "Online FP8", "FP8 checkpoint", "Combined"]
    for y, label in enumerate(names):
        metrics = measured[label]
        score = metrics["filters"]["flexible-extract"]
        if score["n"] != 200:
            raise ValueError("expected fixed first-200 quality subset")
        axis.errorbar(
            100 * score["accuracy"],
            y,
            xerr=[
                [100 * (score["accuracy"] - score["ci_low"])],
                [100 * (score["ci_high"] - score["accuracy"])],
            ],
            fmt="o",
            capsize=5,
            markersize=8,
            color="#2563eb",
        )
        paired = metrics.get("paired", {}).get("flexible-extract")
        note = f"McNemar p={paired['mcnemar_p']:.4g}" if paired else "reference"
        axis.text(99, y, f"{score['correct']}/{score['n']} · {note}", va="center", fontsize=10)
    axis.set(
        yticks=range(4),
        yticklabels=display,
        xlim=(85, 108),
        xticks=[85, 90, 95, 100],
        xlabel="GSM8K flexible-extract accuracy (%) · displayed range zoomed",
        title="Relative quality · fixed first 200 GSM8K problems",
    )
    axis.invert_yaxis()
    axis.grid(axis="x", alpha=0.2)
    axis.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.5,
        0.025,
        "Wilson 95% intervals · greedy raw completions, 5-shot, no chat template/thinking mode\nFour independent evaluations; scheduling-only rows reuse baseline evidence. Not a full-dataset or general quality claim.",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.12, 1, 0.96))
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def plot_qwen_regressions(data, destination):
    """Count stored corrected verdicts while preserving inconclusive comparisons."""
    from collections import Counter

    labels = {r["id"]: r["label"] for r in data["records"]["configs"]}
    measured = {r["config_id"] for r in data["aggregates"]}
    compared = {r["candidate_config_id"] for r in data["regressions"]} & measured
    order = [c["label"] for c in data["records"]["configs"] if c["id"] in compared]
    counts = {
        label: Counter(
            r["verdict"] for r in data["regressions"] if labels[r["candidate_config_id"]] == label
        )
        for label in order
    }
    fig, axis = plt.subplots(figsize=(12, 5.4))
    left = [0] * len(order)
    for verdict, color in (
        ("improvement", "#0f766e"),
        ("no_change", "#cbd5e1"),
        ("inconclusive", "#eab308"),
        ("regression", "#c2410c"),
    ):
        values = [counts[label][verdict] for label in order]
        axis.barh(
            range(len(order)), values, left=left, label=verdict.replace("_", " "), color=color
        )
        left = [a + b for a, b in zip(left, values)]
    axis.set(
        yticks=range(len(order)),
        yticklabels=order,
        xlabel="Workload / load / metric comparisons (not independent experiments)",
        title="Qwen3-8B · Holm-corrected regression verdicts",
    )
    axis.invert_yaxis()
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.28))
    validation = data["validation"]
    fig.text(
        0.5,
        0.025,
        f"{replication_caption(data)} · inconclusive includes MDE gates\nA/A: {validation['false_positives']}/{validation['n_tests']} false positives ({validation['false_positive_rate']:.1%}); overlapping splits, descriptive rate. Only configurations with stored comparisons shown.",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.14, 1, 0.97))
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def main():
    """Rebuild README figures from committed reports and completion counts."""
    directory = ROOT / "reports/readme"
    directory.mkdir(parents=True, exist_ok=True)
    plot_results(ROOT / "reports/gptoss-20261124/report.json", directory / "gptoss-results.png")
    plot_progress(directory / "progress.json", directory / "campaign-progress.png")
    qwen = json.loads((ROOT / "reports/qwen3-20261125/report.json").read_text())
    plot_qwen_performance(qwen, directory / "qwen-performance.png")
    plot_qwen_quality(qwen, directory / "qwen-quality.png")
    plot_qwen_regressions(qwen, directory / "qwen-regressions.png")


if __name__ == "__main__":
    main()
