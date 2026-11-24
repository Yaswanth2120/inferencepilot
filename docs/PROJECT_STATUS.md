# Verified project status — 2026-11-24

The offline implementation and a separate existing-server GPT-OSS performance run
are verified. The original v0.1.0 definition of finished is **not yet met**.
No additional GPU work or rental-control action was performed for this audit.

**GPU access is on hold by owner instruction.** Another project is using the rental.
Do not connect to it, poll it, deploy to it, start GPU work, or stop its services
until the owner explicitly authorizes access again. Subsequent fixes below were
implemented and tested locally using fakes only.

## Verified evidence

- PRs #10 and #11 are merged; all six Linux/macOS × Python 3.10/3.11/3.12 checks for
  the completed-results PR passed. No open PR remained when this audit began.
- The GPT-OSS database says completed: 30 valid reps, six workload/concurrency
  points × five reps, 3,000 requests, 768,000 output tokens, 108.4 minutes.
- Every one of the 30 locally archived raw JSON files was parsed and cross-checked
  again. SQLite integrity_check returned ok.
- All 36 published aggregate rows were recomputed from archived rep summaries
  through the shared analysis/statistics code. Means and CI endpoints matched;
  each row has n_reps=5.
- The saved run used a single already-running A100 80GB server, vLLM 0.32.0,
  GPT-OSS MXFP4, an advertised context limit of 8192, and max_num_seqs=1.
  Higher client concurrency measured queueing behind this scheduler limit.
- Offline implementation, fake pipeline, lifecycle/interrupt tests and statistical
  unit tests have passing CI. Fresh-clone verification is recorded below when complete.

The full raw/DB/log archive is under the gitignored
`data/live/gptoss-20261124/archive/`. Public Markdown/JSON results are in
[`reports/gptoss-20261124/`](../reports/gptoss-20261124/README.md).

## Milestone audit

| Scope | Verified status | What remains | GPU needed? |
|---|---|---|---|
| M0–M8 | Implemented and tested offline | Offline readiness differences fixed; validate them on hardware only after new authorization | No for code fixes |
| M9 Qwen campaign | Scripts, resume tests and runbook prepared; campaign not run | Measured calibration; hardware probes; three independent baseline launches; OFAT/combined/eager runs; chat/RAG/prefix and open-loop data; quality/agreement; real A/A/MDE/corrected comparisons; constrained recommendation | Yes |
| M9 fixtures | One real GPT-OSS vLLM 0.32 smoke fixture committed | Capture actual main-pipeline startup, detailed benchmark and harness fixtures for the chosen supported version; replace or document the provisional fixtures | GPU to capture missing evidence; local work afterward |
| M10 optional GPT-OSS | Existing-server chat/RAG measurements at client concurrency 1/8/32 completed | Cold startup timing, controlled server restarts, context/OOM-boundary checks and actual batching-capable configurations were not measured | Yes if completing this optional scope |
| M11 release | Six-job CI and project docs exist | Finish live evidence and final review; freeze schema, set release version and publish/tag v0.1.0 | No for packaging/docs; release depends on M9 |

M10's original Qwen-first ordering was explicitly overridden by the owner for this
one existing-server run. That does not silently remove the Qwen campaign from the
project definition. The current package version is 0.0.1; no release tag exists.
Unrun live paths are **not run (needs GPU)**.

## Offline readiness fixes after the audit

1. **Report provenance fixed offline.** New runs save explicit `synthetic`, `live`
   or `unverified` declarations in schema_meta. Legacy databases remain unverified;
   neither a GPU name nor measured calibration establishes provenance. Reports and
   plots carry the scope; failed live attempts do not claim successful measurements.
   This is a recorded declaration, not independent hardware certification.
2. **Main-runner telemetry implemented offline.** Before/after-rep sampling now
   includes GPU memory, SM/memory clocks, power, temperature and utilization with a
   timestamp. Unsupported values remain null, and failed queries retain errors.
   The safety preflight is unchanged. The deadline is checked again after sampling.
   Actual hardware behavior of this new path is not run (needs GPU).
3. **Quality scheduling reconciled offline.** Successful GSM8K results are cached
   per experiment/model/precision/seed/protocol, including subset, context and
   harness version. Scheduling-only launches inherit named source evidence; they
   are not independent new quality samples. Precision changes get a new evaluation,
   and the combined candidate always has its own full-config scope. Success and its
   cache pointer commit atomically; failed results are not reused. Agreement still
   runs per launch. The six-launch fake test uses two measured evaluations plus four
   inherited rows. Actual runtime/quality effects remain not run (needs GPU).
4. **Version validation remains a live gate.** The main pin stays vLLM 0.15.1;
   the completed existing-server run used 0.32.0. That separate real fixture does
   not certify pinned Qwen lifecycle, quantization or harness compatibility.
5. **Documentation/packaging readiness.** Stale no-live-results wording was corrected.
   Unused M0/M6 helper messages remain nonblocking cleanup items; current CLI wiring
   uses the actual runner/selftest. The 0.0.1 wheel is checked separately from an
   editable checkout; no release version/tag is published before the live gates.

## Order of remaining work

1. Offline fixes for provenance, telemetry and quality scheduling are implemented
   with focused tests. Keep the main version pin unchanged until targeted live
   compatibility testing is explicitly authorized.
2. On a prepared GPU: run the required M9 design with measured calibration and
   actual probe evidence. Preserve replication and stop at the agreed budget.
3. Locally: verify the archive, replace/document real fixtures, run the full
   statistical/quality/recommendation/report pipeline and inspect final plots.
4. Optionally finish the unrun GPT-OSS startup/context/tuning checks. The existing
   run alone cannot support optimized-batching, max-context or speedup claims.
5. Finish M11 release review and packaging/version/tag only after the required
   evidence exists. Do not mark v0.1.0 complete merely because the benchmark finished.

A GPU is unnecessary for the immediate code/documentation/release-preparation work.
It is still required for the missing live experiments under the current master spec.

## Fresh-clone verification

On 2026-11-24, a new clone of merged commit
`ea02a7a` was installed into a new Python 3.12 virtualenv using the README extras
`.[dev,report]`. Results:

- Editable install succeeded without import-path workarounds.
- `pytest -q`: **283 passed in 111.20 seconds**.
- `ruff check .`: **All checks passed**.
- Standalone `inferencepilot selftest`: passed, including six fake lifetimes,
  120 reps, quality/agreement, resume, regression/A/A, recommendation and report.

This verifies the offline quickstart with the report extra. It is not live model
quality evidence or completion of the other M11 release gates. No additional tests
or measurement-code changes were introduced by the documentation audit.

## Verification of the offline readiness fixes

With the rental left untouched, the local full suite passed **300 tests**, Ruff
passed, and focused provenance/quality/telemetry checks passed. The CLI interruption/
resume test also verified that an explicit synthetic declaration survives resume.
A standard isolated pyproject build produced a 0.0.1 wheel; it was installed into
a separate local environment without an editable path, and its full standalone
selftest passed. Synthetic chart provenance labelling was visually checked.
These checks do not authorize or substitute for new hardware validation.
