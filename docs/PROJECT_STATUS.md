# Verified project status — 2026-11-25

**M9 is complete.** The Qwen3 campaign, final generated report, plots, archive
verification and documented fixture coverage are available under
[`reports/qwen3-20261125/`](../reports/qwen3-20261125/README.md). Package version is
0.0.1; v0.1.0 has not been released. No GPU work is needed for release preparation.

## Verified evidence

- 605/605 valid performance reps, 110,000 requests, 25,344,000 output tokens.
- All 11 launches succeeded: three independent BF16 baselines, supported OFAT
  candidates, combined candidate and seeded eager regression. Five reps per point;
  all eight closed-loop points and three measured-capacity open-loop chat rates.
- The workflow completed in 19.51 wall-clock hours including recovery and automated
  analysis, below the approved 22-hour cap. Commissioning/setup are separate.
- Four independent first-200 GSM8K evaluations; scheduling-only rows inherit named
  sources. Token-ID agreement was captured for all launches with a baseline reference.
- A/A false-positive rate 7/219 (3.20%), 45 inconclusive comparisons; overlapping
  splits are correlated. Eager caused significant regressions on primary metrics.
- The recommended BF16 token budget 2048 meets the saved point-estimate constraints;
  its TTFT CI crosses 500 ms, so the recommendation does not guarantee that SLO.
- The DB, raw arrays, startup/benchmark/harness logs, job histories and report are
  archived locally in `data/live/qwen3-20261124/archive/campaign/` (gitignored).
  SQLite integrity passed; every raw rep was parsed and cross-checked locally.
- All 657 aggregate means, 10,000-resample bootstrap CI endpoints and rep/launch
  counts were independently reproduced through the shared analysis functions.
- Public report copies redact the Vast container label only. Source/public hashes,
  exact archive counts and remaining limitations are in `verification.json`.
- Earlier GPT-OSS existing-server validation remains separately published: 30 valid
  reps, 3,000 requests, 108.4 minutes, max_num_seqs=1 and one server lifetime.

## Findings and limitations retained

The forced-AWQ/BF16 request failed because the pinned explicit AWQ implementation
accepts FP16 only. It is retained as unsupported with the exact error; this is not
a general claim about A100 AWQ support. Both requested FP8 paths loaded and were
measured. Chunked prefill stayed on and KV cache dtype stayed auto; alternative
optional factor levels were not evaluated.

Selection of the combined candidate stopped after 440 valid reps when independent
field choices mixed two precision variants. Commit `bfa5791` made that factor
atomic; resume preserved every checkpoint and the original deadline. Initial code
was `a65db5d`. No measurements, scores, thresholds or constraints changed. Details
are preserved in DECISIONS.md and the archived job/recovery metadata.

[Fixture coverage](FIXTURE_COVERAGE.md) documents real pinned startup, benchmark,
harness and quantized/eager examples, plus every retained provisional fixture and
generic marker. Synthetic edge cases were retained rather than weakened or relabelled.
The main campaign establishes this GPU/model/version scope, not arbitrary-version
compatibility, full GSM8K capability or general quality equivalence.

## What remains

| Scope | State |
|---|---|
| M0–M8 | Implemented and verified offline; live campaign exercised the main path. |
| M9 | Completed campaign, report, local archive verification, README images, real fixture coverage and documented provisional cases. |
| Optional M10 | Existing-server GPT-OSS performance subset done; cold startup/context/OOM-boundary tests are not run (needs GPU). |
| M11 | Final clean-clone/release review, schema/version freeze and v0.1.0 tag remain. |

The existing CLI, quality-cache lineage, telemetry, provenance and recovery tests
remain in the suite. The release must still pass the six Linux/macOS × Python
3.10/3.11/3.12 CI jobs and a clean-environment quickstart. Do not treat optional
unrun experiments as completed. No rental stop or destruction was automated.

Final M9 publication checks: **316 tests passed in 158.10 seconds**; Ruff passed.
The focused report integration check passed after the label-layout change. All
final images were rendered and visually reviewed, and README/report links resolve.
