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
    fig.suptitle("Qwen3-8B campaign · work in progress", fontsize=16, fontweight="bold")
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
        "Count-based progress, not a completion-time estimate. Final comparisons and recommendation are pending.",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0.02, 0.13, 0.98, 0.83))
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def main():
    """Rebuild both README images from their committed source files."""
    directory = ROOT / "reports/readme"
    directory.mkdir(parents=True, exist_ok=True)
    plot_results(ROOT / "reports/gptoss-20261124/report.json", directory / "gptoss-results.png")
    plot_progress(directory / "progress.json", directory / "campaign-progress.png")


if __name__ == "__main__":
    main()
