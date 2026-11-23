# Decisions

## M0 — scope and truthful status

Implement only the M0 package, environment inspection, and fakes. Future
production modules and campaign commands are not empty implementations. The
selftest returns success for CLI wiring but explicitly says the full pipeline
is pending M6. Campaign/report Makefile targets fail instead of pretending to run.

## M0 — fake contract and fixtures

All fake flags are provisional constants in vllm_flags.py. No production flags
are in use yet, so USED_FLAGS is empty; M1 must populate it from real command
builders, pin vLLM, and validate help, including the missing-flag test. Fake
startup logs include a vLLM-shaped engine line and a clearly marked JSON config.
The fake bench generates deterministic arrays rather than implementing a load
generator. Real CLI defaults, full schema, and parsers require M1/M4/M9 validation.
Sources are linked in tests/fixtures/provisional/README.md.

## M0 — determinism and failure controls

A request's delay schedule depends on server seed plus explicit request seed;
therefore repeated requests are reproducible without depending on arrival order.
Concurrency scales delays from the number of active generation requests at entry.
Failure/hang selection uses a separate server-seeded RNG; concurrent failure
assignment consequently follows arrival order. A hang defaults to an hour and
is cancellable; tests shorten it or cancel the request. Synthetic whitespace
tokens intentionally do not simulate any real tokenizer or quality.

## M0 — subprocess ownership

The fake starts one real sleeping child and reaps it on normal shutdown or
SIGTERM. Tests signal the parent alone, assert the child PID disappears, and
use an isolated process group for emergency test cleanup. This validates the
fake itself; production ServerManager safety and teardown remain M3.

## M0 — environment and privacy

Read package versions via distribution metadata, and read CUDA's literal value
from torch/version.py with AST parsing, without executing torch or vLLM.
Record the nvidia-smi driver report separately because its CUDA capability is
not the installed runtime version. Missing information remains null or an
explicit unavailable result. Hash pip freeze rather than storing it, and only
capture the two named Vast identity variables; do not dump the environment.
CPU and RAM inspection have platform fallbacks. No Git repository existed at
kickoff, so a missing SHA is reported rather than inventing provenance.

## M0 — verification boundaries

Local verification uses macOS and Python 3.12.9. CI defines macOS/Linux and
Python 3.10–3.12, but its result is unverified until run on a remote runner.
Real GPU paths: not run (needs GPU). No vLLM pin or novel sweep claim is made
before M1's required release-specific investigation.

## M0 — local virtualenv directory

The workspace repeatedly sets the macOS hidden flag on `.venv` contents;
Python 3.12 skips hidden .pth files, breaking editable imports. Use `venv/`
locally and in the quickstart. Do not mask the failure with PYTHONPATH or
change the subprocess assertions. Both environment directories are gitignored.

## Repository setup after M0

The owner explicitly authorized a public GitHub repository and selected public
visibility. Preserve M0 in its own conventional commit and historical feature
branch; put MIT licensing and workflow setup in a separate main commit.
Use PRs and squash merges, with six required OS/Python checks, linear history,
resolved conversations, up-to-date branches, and no force pushes or deletion of
main. The owner is a solo maintainer, so external review approval count is zero.
Local Git configuration uses fast-forward-only pulls, simple pushes, and pruning.

The owner requested branches for every milestone. Create named reserved branches
at the setup commit rather than pretending future work is already implemented.
Their first use must incorporate latest main. Create bug branches for actual
fixes, not arbitrary empty references. This is documented in CONTRIBUTING.md;
M1 is proposed as a PR rather than merged without review.

## M1 — pin and prior art before implementation

Pin vLLM 0.15.1, a version with documented sweep and required serve options,
for a reproducible first adapter contract. This is not a claim to use the newest
release. Its sweep tool already covers server startup, configuration exploration,
repeated runs, resume, and SLA tuning; none of those alone are novel. Document
the overlap and intended later statistical/quality contributions in
VLLM_COMPATIBILITY.md. No real vLLM was installed or executed.

All flag literals and the declarative ConfigSpec-to-option mapping remain in
vllm_flags.py; ConfigSpec.argv performs only the pure mapping, not I/O.
Doctor checks the exact pinned version and serve flags; benchmark verification
will be registered with the M4 production builder. Use full-help mode because
the pinned parser groups ordinary help. The fake simulates that mode and can
omit an option to test a version mismatch realistically.

## M1 — canonical input and reproducibility

Reject unknown fields, nonfinite numbers, duplicate factors/workloads, invalid
model/quantization pairs, out-of-range inputs, noncanonical campaign factor
levels, and invalid token-budget combinations. The baseline is the exact BF16
reference in section 5.2, with configurable port and server seed. Reps remain
five; reducing reps requires the owner's explicit statistical tradeoff later.
The plan JSON sorts keys and has no timestamp or output path. Seeded schedule
randomization and request seeds are separate RNG uses so candidate membership
cannot change the input data at other points.

Per-point rep seeds are shared across configurations and independent launches,
keeping synthetic prompt input comparable; launch independence comes from a
server restart, not a changed request dataset. Seeds are stored explicitly and
must be honored by M6. The experiment seed randomizes design; baseline.seed is
the independently recorded server seed. Dry-run reconstructs derived data from
the embedded experiment and rejects modified/stale schedules and estimates.

## M1 — baseline order ambiguity

Section 5.2/acceptance require first, middle, last baseline placements, while
section 16's illustrative run order puts combined and seeded regression after
the last baseline. For the M1 plan, use section 5.2's explicit acceptance rule:
baseline indices 0, floor(total_launches/2), total_launches-1. Shuffle OFAT
candidates only, then schedule combined after all OFAT results, then seeded
eager regression, with the final baseline bookending everything. This satisfies
drift coverage and data dependencies. Reconcile the illustrative live runbook
with this order before M9 rather than silently moving a baseline.

## M1 — deferred combined configuration and probe gates

No OFAT results exist when the initial plan is created, so the combined entry
has spec=null and pending_selection, with a reserved launch slot. Do not invent
best levels or label an untested combination a winner. M6 must fill it from
supported measured individual results and validate the new ConfigSpec before
execution. All weights start pending until load evidence exists. Optional
chunked-prefill-off/FP8 KV factors need explicit probe evidence before inclusion;
unsupported variants stay in plan.configs with evidence but get no launch.
A failed baseline probe prevents a meaningful comparison plan.

## M1 — calibration estimate and budget scope

Calibration records per-point measured-rep seconds excluding warmups, startup,
teardown, source, evidence note, and an explicit extra reserve. Per launch:
startup + teardown + sum_over_points(5 * rep_seconds * (1 + warmups/num_prompts)).
Total hours = (number_of_launches * per_launch_seconds + extra_seconds)/3600.
This warmup reserve assumes per-request average time and is approximate under
concurrency; different configurations may have different duration.

The example uses clearly labeled synthetic values: 1722 seconds per launch,
12 launches plus 600 extra seconds = 5.906666... hours. It is a demonstration,
not measured capacity. Combined uses the same provisional calibration estimate.
Open-loop rates and their time require measured baseline capacity and are
explicitly deferred to M4/M6, excluded from this estimate. Warn before execution
and budget for them separately. M1 shows budget overrun warnings and rejects
nonfinite/nonpositive overrides; actual wall-clock budget enforcement is M6.

The example keeps workloads and calibration in one YAML document so the
validated experiment is self-contained. Separate workload-file composition is
not required for M1 and no second source of truth is introduced.
