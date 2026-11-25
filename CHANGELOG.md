# Changelog

## 0.1.0 — 2026-11-25

First release of InferencePilot, a CLI for reproducible vLLM serving comparisons.

### Included

- Validated configurations, deterministic OFAT plans, three baseline launches,
  five reps per point, measured-budget estimates and a tested combined candidate.
- Owned server lifecycle, readiness/resolved logs, hardware preflight and telemetry.
- Detailed vLLM benchmark adapter with raw-metric cross-checks, failure counts,
  open-loop loads, atomic SQLite checkpoints and interrupt/resume support.
- Pure Python bootstrap/permutation statistics, Holm correction, launch-aware MDE,
  regression verdicts, A/A validation and a reproducible synthetic power study.
- Pinned lm-eval raw-completion quality, paired McNemar/Wilson results, greedy
  token-ID agreement, explicit quality-source reuse and constrained recommendations.
- Markdown/JSON reports, plots, offline fakes and Linux/macOS Python 3.10–3.12 CI.
- Completed Qwen3-8B campaign: 605 valid reps, 110,000 requests, 11 successful
  launches, verified off-rental archive, real fixtures and final README figures.
- Separate GPT-OSS existing-server performance results: 30 reps, 3,000 requests.
- MIT license, wheel/source distributions, `--version`, and frozen SQLite schema v1.

### Findings and limits

The best tested configuration under the saved constraints is BF16 with token
budget 2048. At chat concurrency 32, mean rep-p95 TTFT was 476.91 ms but its 95% CI
extends to 507.26 ms, so point-estimate eligibility does not guarantee the 500 ms
SLO. Faster FP8 candidates failed that constraint. Eager's seeded regression was
detected; A/A recorded 7/219 false positives with correlated, overlapping splits.

Quality is relative on the fixed first 200 GSM8K problems, not general equivalence.
The requested forced-AWQ/BF16 method was rejected; no general A100 AWQ limitation
is claimed. Unobserved interfaces and synthetic edge cases remain documented.
The live combined-selection bug was fixed by choosing the precision tuple atomically;
all 440 prior reps were preserved when resuming under the original deadline.

Optional GPT-OSS cold-start/context/OOM-boundary tests were intentionally omitted
from this release: **not run (needs GPU)**. Multi-GPU, other serving engines,
training, Kubernetes, web UI and cloud rental management remain outside scope.
