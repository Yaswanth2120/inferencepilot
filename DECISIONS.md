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

## M2 — numeric API and descriptive definitions

Stats functions are pure and accept finite scalar real observations. Reject
booleans, strings, NaNs/infinities, empty data, invalid counts/probabilities,
and insufficient data instead of silently dropping or coercing observations.
Use math.fsum for sums, sample SD (n-1), and dimensionless CV=SD/abs(mean).
A zero-mean CV or percent MDE is undefined and raises ValueError.
Percentile p is in [0,100]: after sorting, h=(n-1)*p/100, i=floor(h), j=ceil(h),
w=h-i, result=(1-w)*x[i]+w*x[j]. This is the default linear/type-7 definition
in [NumPy's documentation](https://numpy.org/doc/stable/reference/generated/numpy.percentile.html).
The implementation uses a convex weighted sum to avoid overflowing x[j]-x[i]
for large opposite-sign finite endpoints. Tests use hand calculations, not NumPy.

## M2 — bootstrap and permutation conventions

Bootstrap CI estimates the mean of scalar rep-level statistics. Draw n reps
with replacement for each of 10,000 resamples, using a private seeded RNG;
take the two percentile endpoints at (1-confidence)/2 and its complement.
At least two reps are needed. This resamples neither raw request latencies
nor launches; the between-launch noise is accounted for separately by MDE.
It assumes rep-level exchangeability. Actual clustered-data calibration must
be assessed in M7, so do not claim guaranteed coverage or power from M2 tests.

Permutation statistic is absolute difference of sample means (two-sided).
Enumerate distinct assignments of labeled pooled positions to the original
sample sizes if C(N,n_baseline)<=20,000; repeated numeric values still occupy
different positions. Exact p is the fraction with distance >= observed.
For larger problems, uniformly sample 100,000 assignments with replacement
and use p=(extreme+1)/(draws+1), preventing a simulated zero p-value. This
conservative convention is described in the [SciPy permutation documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).
Our two-sided absolute-distance rule is explicit and is not necessarily the
same as doubling a one-sided tail for asymmetric unequal-size samples.

Center pooled data before the permutation sums to reduce offset cancellation.
Treat floating-point distances as tied at relative tolerance 1e-12 and zero
absolute tolerance so tiny measurement units do not turn distinct values into
ties. The result records method, assignments evaluated, possible assignments,
and Monte Carlo seed. Optional counts/limit parameters support explicit
experiments/tests; specified production defaults remain 20k/100k.
No function changes the caller's data or global random state.

## M2 — Holm and paired proportions

Holm sorts m p-values, multiplies the smallest by m, the next by m-1, and so on,
takes the running maximum, clips at 1, and restores original order. Empty
families return an empty list. Correction scope remains all tests in one
candidate-versus-baseline comparison, as specified for M7.

Wilson uses the two-sided score interval without continuity correction with
z=Phi^-1((1+confidence)/2): center=(p+z^2/(2n))/(1+z^2/n),
radius=z*sqrt(p(1-p)/n+z^2/(4n^2))/(1+z^2/n). Clamp roundoff to [0,1].
This matches the score method described by [NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
Require integer 0<=successes<=n and n>=1.

Exact McNemar takes only the two discordant counts b and c. Under the null,
B~Binomial(b+c,1/2); p=min(1,2*sum_{k=0}^{min(b,c)} C(b+c,k)/2^(b+c)).
With no discordances, return 1. Concordant cells do not contribute. Use
integer combinations and a single final ratio, avoiding early exponential
underflow. This is the exact-binomial convention in [statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html),
not the asymptotic or mid-p variant. Those libraries are references only;
neither is a dependency or imported by the implementation/tests.

## M2 — MDE derivation and assumptions

Model baseline rep j of independent launch i as y_ij=mu+u_i+e_ij, with
Var(u_i)=tau^2, Var(e_ij)=sigma^2, and independent zero-mean launch/rep effects.
The estimated candidate shares these variance components; with only one
candidate launch we cannot independently estimate its between-launch variance.
Require at least two baseline launches and two reps in each. Unbalanced
baseline counts are supported because interrupted/partial runs may leave them.

For K baseline launches with sizes n_i, N=sum(n_i), launch means m_i and
rep-weighted mean mu_hat=sum(n_i*m_i)/N:

- MS_within=sum_i sum_j (y_ij-m_i)^2/(N-K).
- MS_between=sum_i n_i*(m_i-mu_hat)^2/(K-1).
- n0=(N-sum_i n_i^2/N)/(K-1).
- sigma_hat^2=MS_within.
- tau_hat^2=max(0,(MS_between-MS_within)/n0).

These are the one-way random-effect method-of-moments components documented
by [NIST](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/onewayan.htm).
The nonnegative truncation avoids a negative estimated noise variance; it
does not prove launch effects are absent. If every observation is constant,
both components and plug-in MDE are zero, a property of this estimator.

A baseline grand mean weights launch i by w_i=n_i/N, so
Var(baseline_mean)=tau^2*sum_i w_i^2+sigma^2/N.
For C independent candidate launches with R reps each,
Var(candidate_mean)=tau^2/C+sigma^2/(C*R).
Independent baseline and candidate noise therefore give:

V=tau_hat^2*(sum_i w_i^2+1/C)+sigma_hat^2*(1/N+1/(C*R)).

For the planned K=3 equal launches of 5 reps and C=1,R=5,
V=(4/3)*tau_hat^2+(4/15)*sigma_hat^2. Crucially, increasing candidate reps
does not remove its one-launch noise term tau_hat^2.

With approximately normal mean difference and known plug-in standard error
SE=sqrt(V), a two-sided alpha test uses z_(1-alpha/2)*SE. A worse-direction
mean shift delta has approximately power Phi(delta/SE-z_(1-alpha/2)), ignoring
the negligible opposite tail at the design point. Solving for target power
q gives delta=(z_(1-alpha/2)+z_q)*SE. Report
MDE_pct=100*delta/abs(mu_hat), with alpha=.05 and power=.80 by default.
Their quantile sum is 1.959963984540054+.841621233572914=2.801585218112968.
Power must be >.5 for this one-tail-dominant planning approximation.

This is a nominal unadjusted-alpha planning estimate, not an exact finite-sample
power result for the later permutation/Holm detector. Three launches give an
uncertain variance estimate; normality, independence, shared baseline/candidate
variance, and ignoring the second tail are assumptions. M7 must measure false
positives and power with launch noise and multiple testing, and report any
failure honestly. Never interpret this plug-in formula as validated detector power.

Worked balanced example: launches [8,10],[10,12],[12,14] have mean 11,
MS_within=2, MS_between=8, n0=2, tau_hat^2=3. With C=1,R=2,
V=3*(1/3+1)+2*(1/6+1/2)=16/3, giving
MDE_pct=100*2.801585218112968*sqrt(16/3)/11.
The tests also derive an unbalanced example (sizes 2,3,2) by hand.
The result carries all components, counts, alpha, and target power for auditing.

## M2 — branch dependency and CI

M1 remains an open PR; one cancelled duplicate PR check was rerun rather than
bypassing protection or asserting it passed. Fast-forward reserved M2 to the
M1 head, then propose M2 as a stacked PR targeting the M1 branch. Broaden the
CI pull_request trigger to every base branch so a stacked PR gets the same
six OS/Python checks. Keep the existing tests and protections unchanged.
The duplicate push/PR workflow behavior predates M2 and is not otherwise
redesigned here. No earlier milestone implementation is changed in M2.

## M3 — merging the prerequisite PRs

The owner explicitly requested all existing PRs merged before progressing.
Squash merge M1 with required checks green, rebase only M2's changes onto the
resulting main using a lease-protected feature-branch push, and retarget M2 to
main. The installed gh CLI's PR-edit operation failed on a deprecated Projects
query, so use the supported GitHub REST update instead. A metadata retarget did
not create the required new-head checks, so add an empty CI refresh commit.
Enable repository auto-merge and queue M2 only behind its required checks; no
admin override, status-check removal, or direct main push is used.
While those jobs queue, M3 work is based on the complete M2 tree; reconcile its
branch with the squashed main before creating the M3 PR.

## M3 — ownership and failure records

Use one ServerManager per active launch with POSIX start_new_session, assigning
the owned group only after Popen succeeds. Signals are restricted to that
recorded group. Port, GPU, process-list, and flag checks are read-only and never
supply a PID to the signaling path. A second start refuses until the prior
launch is cleaned up. stop before start is harmless; repeated stop is idempotent.
No global process-kill command or discovery-based termination is implemented.

LaunchResult is an in-memory dataclass with the schema-compatible status and
lifecycle fields plus cleanup_complete. Persistence into the exact SQLite
schema remains M6. Preflight failures are server_failed even in probe mode,
because a busy port/GPU or missing tool does not establish unsupported hardware.
After our process starts, load-probe startup failure is labeled
unsupported_on_hardware, retaining the reason and log tail. That label records
an unsuccessful load, not an experimentally proven hardware root cause.
Cleanup failure takes precedence as server_failed, preserves both diagnostics,
and prevents the next launch. Interruptions record aborted and attempt cleanup.

## M3 — safety checks and units

Interpret the section 12 idle threshold as 2048 MiB, consistent with the units
reported by nvidia-smi; exactly 2048 is refused. Query memory.used in unformatted
numeric CSV, require exactly one visible GPU, and reject unknown, negative, or
nonfinite output. No opt-out bypass is added. The NVIDIA [query reference](https://docs.nvidia.com/deploy/nvidia-smi/)
and [query examples](https://nvidia.custhelp.com/app/answers/detail/a_id/3751/~/useful-nvidia-smi-queries)
are the sources for the executable's flags; no NVIDIA executable was run locally.

Read ps executable/module identities rather than any occurrence of the word
vllm. Detect console scripts, Python module invocations, and VLLM worker names.
Malformed or unavailable inspection fails closed. Diagnostics retain only PID
and executable, not full arguments that may contain an API key. Port bind uses
SO_REUSEADDR so leftover TCP TIME_WAIT does not falsely occupy a reusable port;
it still rejects another active listener. These checks reduce conflicts but
cannot atomically reserve the GPU/port against an unrelated concurrent launcher.

## M3 — readiness, logs, and version checks

Preflight reuses doctor's executable-version/full-help checks. The existing
ConfigSpec argv mapper remains the only builder and all vLLM spellings remain
in vllm_flags.py. Startup timing begins immediately before Popen. Health and
models must both return success, models must contain the requested served name,
and the owned process must still be alive. HTTP calls use a bounded timeout,
ignore proxy environment variables for localhost, and poll until the configured
900-second default readiness deadline.

Logs use a validated filename-safe launch ID and exclusive creation; neither
an existing log nor a probe JSON file is overwritten. Errors retain the last
200 log lines using a streaming deque. Parsing strips ANSI for matching, keeps
raw matching lines, accepts engine-field spelling variants, and lets later
resolved settings override earlier ones. Missing values remain absent. Capture
context, prefix/chunk states, chunk budget, quantization/KV dtype, KV token
capacity and maximum concurrency, backend, and graph mode when observed.
No startup text is eval'd. All parsers/fixtures remain provisional until M9.

## M3 — teardown and process-state race

Signal the owned process group with SIGTERM, allow 60 seconds, then SIGKILL
and a further bounded 10-second exit wait. Reap the parent, close its log, and
poll GPU release for up to 120 seconds. A timeout or unknown state records a
cleanup error and retains the next-start gate; clearing the error condition
allows an explicit subsequent stop to finish cleanup. The prior launch's
failure status remains a truthful record even after cleanup succeeds.

During the full macOS test suite, killpg(group,0) intermittently raised EPERM
around process exit. Replace that existence probe with read-only ps group/state
inspection, not a blanket permission-error suppression. Zombies cannot execute
or retain a GPU context, so they do not keep an owned group active; the manager
still waits/reaps its direct parent. If an actual signal returns EPERM, suppress
it only after independent read-only inspection confirms no active group member
remains. Otherwise fail closed. Both cases have tests. Detached descendants in
a different session/group are outside this group-ownership cleanup mechanism;
preflight and GPU-release checks remain safeguards, not a claim to kill them.

## M3 — probes and offline evidence

Weight probes validate the selected model/quantization, start with load-probe
classification, stop, and save JSON evidence. Chunked-prefill runs both boolean
directions and requires observed values equal to requests for factor_honored.
Missing/ignored values yield not_honored. FP8 KV probes similarly require the
resolved cache dtype. A failed cleanup halts the remaining probe configurations
and remains in JSON. This command does not silently modify an experiment YAML;
the owner can review its evidence before including optional factors.

Extend only fake controls needed for startup testing: crash diagnostics, a
never-ready process, health failure, wrong served model, and forced-on chunked
prefill. Add synthetic KV/backend/graph lines without claiming they are real
GPU output. Integration fixtures put fake nvidia-smi and a preflight ps shim on
PATH; group-exit inspection delegates to the real OS ps so actual child cleanup
is still verified. No GPU/vLLM path was run: not run (needs GPU).

## M4 — pinned source investigation and scope

The owner authorized M3's merge; all six required jobs were green. Squash
merge PR #3 and advance the reserved M4 branch from the updated main. Implement
only the benchmark command/parser and metrics layer. Actual invocation,
checkpointing, raw-path ownership, analysis CLI/store integration, and budget
scheduling remain M6 rather than building a second runner in this milestone.

Inspect the exact vLLM 0.15.1 sources before defining flags or result semantics:
[serve.py](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/benchmarks/serve.py),
[endpoint_request_func.py](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/benchmarks/lib/endpoint_request_func.py),
and [datasets.py](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/benchmarks/datasets.py).
These are references, not local imports. Real GPU/vLLM paths: not run (needs GPU).
M0's fake E2E array was explicitly provisional; refresh that fake artifact to the
actual consumed schema as part of M4 rather than teaching production code to
trust a field the pinned tool does not export.

## M4 — command contract and load modes

Add separate LoadSpec and SLOSpec data models without changing M1's serialized
closed-loop plan schema. LoadSpec requires exactly a positive concurrency for
closed mode or a positive finite arrival rate for open mode. Strict new numeric
fields reject booleans/strings. A complete SLO triple is nonnegative milliseconds.

Build argv only from centralized BENCH_FLAGS. Always select openai raw streaming
completions, the exact model/host/port, stored rep seed, fixed input/output length,
ignore_eos, temperature zero, warmup count, saved details, and percentile metrics
TTFT/TPOT/ITL/E2E with p50/95/99. Random-range-ratio zero fixes requested lengths.
For the prefix dataset use one shared prefix, not the tool default ten, so
2048+256 input and 128 output express the specified shared-prefix workload.
The source spelling is prefix_repetition, not the prose hyphenation.

Closed mode passes request-rate inf plus max-concurrency; open mode passes a
finite rate with burstiness 1 and omits max-concurrency to avoid turning a
Poisson arrival-rate test into a concurrency-capped measurement. A provided
SLO emits all three tool goodput pairs with ms units. Register every benchmark
flag in USED_FLAGS so doctor checks the complete serve and bench help outputs.
The builder performs no I/O; M6 must provide unique raw paths and skip completed
reps on resume. No path-creation/overwrite protection is falsely claimed here.

## M4 — raw result validation and E2E limitation

Validate the consumed generation fields strictly: one openai backend, a positive
benchmark duration/prompt count, finite nonnegative timings/counts, aligned
input/output/TTFT/gap/error arrays, and consistent completed/failed counts.
An empty per-request error means transport success; its fixed-length output
validity is a separate metric decision. This permits an HTTP-successful but
zero-token response to be counted as truncated rather than silently dropped.
If tool outcomes cannot be reconciled with error records, reject the artifact
as adapter-broken instead of guessing which requests succeeded. Failed-request
output_lens must be zero, as in the pinned serializer. Metadata not used by
metrics is ignored, including any extraneous legacy e2els array.

The pinned result has no per-request E2E array. For the openai completion
backend, reconstruct E2E=TTFT+sum(stream_gaps), using the source's successive
stream timestamps. The first timestamp and TTFT are read separately, so the
reconstruction may have a small positive clock-reading skew. It is not an
independent exact latency observation. Require reconstructed p99 to agree
within 1% with the tool's E2E p99 and retain a provisional-source note. A real
fixture may expose a limitation; fail visibly rather than assuming the skew is
small enough. Only this backend is supported: openai-chat may also time usage
chunks differently and is rejected rather than silently reusing this formula.

Do not require gap count=output_tokens-1: the pinned code explicitly notes token
bundling and may also record empty finish chunks. Pooled ITL describes observed
stream gaps; TPOT=sum(gaps)/(actual_output_tokens-1) is the per-request mean
output-token decode time. For zero/one-token outputs there is no TPOT distribution
sample. Goodput alone treats it as zero, matching the tool's documented code path.

## M4 — metric populations, n, and failure thresholds

First cross-check all transport successes, including fixed-length violations,
against tool mean TTFT, p99 E2E, request throughput, and output throughput.
Relative difference uses the independently recomputed value as denominator;
exactly 1% is allowed and greater than 1% raises AdapterBrokenError. A recomputed
zero requires a reported zero. Integer token totals must agree exactly, not
within a relative tolerance. Parser/schema failures use the same explicit
adapter-broken error class. Future orchestration must not treat adapter corruption
as a server regression or silently proceed with those metrics.

Own latency distributions and SLO goodput exclude transport failures, truncated
outputs (<requested length), and overlong outputs (>requested length). Report
the latter two separately so a short response cannot appear as improved latency.
Physical output/request throughput remains total delivered output tokens and
transport-completed requests divided by measured duration, including short
responses, matching the tool definition. It is explicitly distinct from full-length
SLO goodput. This avoids an unavoidable false cross-check mismatch if valid-only
latency populations were used to recreate tool numbers that include truncations.

Effective failures are transport failures plus output-length violations. More
than 1% makes a rep partial and ineligible; exactly 1% remains ok with notes.
Use integer failed*100>attempted to avoid threshold rounding. If no valid full
requests remain, label failed. Distributions carry observation counts and ms
units; empty distributions have n=0 and None values, never made-up zero latencies.
Pooled ITL n is gap count, TPOT/TTFT/E2E n is valid request count. Rate n is total
measured attempts, with numerator count, duration, units, and separate outcome
counts also retained. No invalid requests are silently discarded from reporting.

## M4 — measured capacity and open-loop rates

The caller supplies only baseline/chat/closed-loop measurements grouped by
configured concurrency. Exclude partial/failed reps, average comparable rep
request-throughput within each point, then take the maximum tested point mean.
This uses the stated rep unit and does not select a lucky single rep. On equal
means select the smaller concurrency. Keep the selected point's rep count and
the total number of excluded reps across the input points. The helper cannot
infer baseline/workload provenance from a bare numeric rate; future M6/store
selection is responsible for supplying the correct context.

Require a positive finite CapacityEstimate with at least one comparable rep to
derive open-loop LoadSpecs at 50%, 80%, and 95%. Do not guess request throughput
from max_num_seqs or configured concurrency. These helpers resolve rates after
measurement; M1's initial plan continues to show open-loop runtime as deferred
until the later runner integrates calibration and these measured rates.

## M4 — synthetic benchmark fixture behavior

The fake accepts the full new benchmark argv and emits pinned-shape detailed
arrays, counts, backend, and required tool summaries without importing library
metrics or running a load generator. It simulates closed lanes or spaced open
start times deterministically, not actual Poisson/HTTP load or GPU behavior.
Warmups are accepted but not emitted among measured arrays. Fake-only controls
inject process failure, request failures, short output, and latency scaling.
These are synthetic contracts, not serving performance evidence. Its percentile
calculation is independent of stats.py so a shared implementation cannot make
an adapter bug self-confirming. Hand-worked fixtures provide the primary check.

Reject a nonfinite recomputed cross-check value explicitly: a finite tiny raw
duration can otherwise overflow throughput, and inf > inf is false when comparing
an infinite difference against an infinite tolerance. This must never publish an
infinite rate as a validated metric.

## M5 — sequential M5–M8 authorization and quality contract

The owner explicitly authorized completing and pushing M5 through M8 in order,
overriding the default one-milestone-per-session protocol. Keep independent
milestone commits/PRs and run the required checks at each boundary. M4's final
macOS job was cancelled before any steps ran, not a code failure; rerun it and
merge only behind required checks. Do not weaken protection.

Pin lm-eval[api] to 0.4.9.2 for its versioned CLI and gsm8k task config. The
builder uses local-completions, five fixed few-shot examples, seed, greedy
raw completions and 512 maximum generation tokens. Full evaluation is 1319
problems; an explicit integer limit means first N dataset rows. No chat template
or thinking setting is applied; these are relative precision comparisons, not
absolute model capability scores. The harness and datasets were not run locally.
Sources: https://github.com/EleutherAI/lm-evaluation-harness/tree/v0.4.9.2 .

The provisional sample schema has one row per document/filter and numeric
exact_match. Require both strict-match and flexible-extract, unique IDs and
nonempty document/prompt hashes. Pair by IDs, not file order, and reject changed
hashes. Accuracy uses Wilson; discordant paired counts use exact McNemar from
stats.py. Greedy agreement requires actual integer token IDs returned via the
pinned vLLM logprobs token_id:N option; never tokenize decoded text heuristically.
The 200 fixed arithmetic prompts are synthetic agreement probes. Divergence is
zero-based, excludes exact matches, and uses the shorter length for strict
prefixes. A no-divergence mean is absent, not fabricated zero.
Live harness/vLLM paths: not run (needs GPU).

### M6 — persistent execution and resume

The owner explicitly requested sequential milestones through M8, overriding the usual one-milestone session limit. The section 11 DDL is copied verbatim, with schema version 1 in schema_meta; execution checkpoints also use schema_meta rather than changing the contract. A database lock excludes concurrent runners. A rep and its logical checkpoint commit atomically, so an interrupted slot starts a new physical server lifetime while completed logical reps remain attached to their original launches. SIGTERM/SIGINT clean up owned processes; SIGKILL cannot promise cleanup and foreign processes are never adopted or killed.

The wall-clock cap starts at experiment creation and includes paused time; resume does not replenish it. Server startup failures are recorded and the schedule continues. The combined configuration chooses improved individual levels by maximum observed closed-loop chat output throughput and receives its own validation launch; equal scores keep the baseline level. The baseline's first measured closed-loop chat sweep fixes all open-loop arrival rates; these additional points were explicitly excluded from the original estimate. Quality is conservatively rerun for each physical completed launch, including scheduling-only configurations; failed evidence remains explicit and will disqualify a recommendation. Small quality subsets and fewer agreement prompts exist only in explicit synthetic selftests, never the default live run.

The selftest command intentionally replaces the M0 stub with a full fake subprocess campaign; its original assertion was updated to the new success message. Fake benchmark timing was separated from FastAPI imports to avoid starting an HTTP framework for every synthetic benchmark. Analysis-owned regression/recommendation tables are initialized here and populated by M7/M8, rather than inserting placeholder conclusions in M6. No GPU or real vLLM was run.

The pre-M6 CLI test expecting an unimplemented runner now checks the required database argument, preserving exit code 2 for configuration errors.

### M7 — detector and offline validation

Comparisons resample whole rep metrics independently in each arm for 10,000 bootstrap draws. Percent effects require positive baseline observations; undefined comparisons remain inconclusive and still occupy a Holm family slot with p=1. Holm is applied across all observed workload/point/metric cases for one candidate, including missing-arm cases. Baseline launch groups remain intact for the random-intercept MDE. The MDE gate overrides otherwise significant findings; the reported MDE remains the nominal normal planning approximation, not a promise of achieved power under multiplicity.

A/A uses every leave-one-baseline-launch split and counts both regression and improvement as false directional findings. Splits overlap, so its count-backed rate is descriptive, not a binomial confidence claim. Incomplete baseline launches from interruptions remain distinct physical lifetimes and cannot silently become complete replicates. The power artifact uses repeated independently seeded fake HTTP ASGI timing responses (synthetic scheduler time, excluding host scheduling noise), with ±0.2 percentage-point launch noise and 0.5% token jitter. It validates one primary latency metric per family and does not predict real GPU power for the larger corrected family. At 2% a correct detector intentionally never calls a 5%-threshold regression; an injected 5% effect can fall on either side of the threshold due to noise. No thresholds were tuned after observing results. The eager config is recognized by role, but whether it is a real regression is not run (needs GPU).

### M8 — constrained recommendation and evidence reports

SLO constraints explicitly name a workload, mode and load. They compare the mean of rep-level p95 estimates to the requested limits, not a pooled percentile or an upper confidence bound; reports keep bootstrap CIs and rep counts visible. Every objective/SLO metric needs at least five comparable reps. Optional request_slos define a separate TTFT/TPOT/E2E request-level goodput triple by workload, passed to both the benchmark argv and raw-derived metrics. Unconfigured goodput is absent, never zero. Paired flexible-extract quality must satisfy drop≤1 pp and McNemar p≥.05 by default; this is an acceptance policy, not proof of equivalence. Missing quality or successful resolved-launch evidence rejects the configuration.

Survivors rank by observed output throughput at the explicit objective point; ties use stable labels. Pareto dominance requires weakly better throughput, E2E and quality with at least one strict improvement. Each survivor carries its comparison MDEs/verdicts, and rejection reasons retain numeric excess and n. The baseline is eligible as a measured choice. The report embeds complete persisted rep summaries and plan/environment provenance in JSON, with raw-file references for the archived database; Markdown and optional matplotlib plots share the same computed aggregate objects. Latency tables label mean-of-rep percentiles and refuse measurement rendering without a positive count. Re-analysis replaces regression rows transactionally; recommendation runs are retained as timestamped history.

The complete selftest now fills the analysis-owned regression and recommendation tables, completing the M6 whole-pipeline requirement without fabricated placeholders. The committed fake demonstration has six server lifetimes, 120 reps, quality, agreement, A/A, regression, recommendation, and inspected PNG plots. Fake benchmark configurations intentionally have no actual model-performance differences; equal observed means are not claimed improvements.

The GPU handoff scripts/runbook are M9 prerequisites delivered alongside M8, not a claim that M9 ran. Preview is the default; execution requires measured calibration, resolved probes and an in-budget plan. A one-rep-per-point baseline calibration helper retains raw detailed evidence; its fixed one-hour extra reserve is explicitly provisional, to be reviewed on the host. A consistent SQLite backup is made through the backup API before rsync, preserving WAL checkpoints without deleting destination data. Both shell scripts were syntax/help checked, and fake calibration, WAL backup and synthetic-execution refusal have offline integration coverage. No GPU was rented, no real vLLM was executed, and no release tag is created before the live evidence and M11 gates.

The M8 fake plan additionally retains a deliberately unsupported AWQ fixture, clearly marked synthetic, without launching it. This exercises actual rejected-configuration reasons in the committed report and makes no A100 compatibility claim. Calibration's owner-run entrypoint also converts SIGTERM into cleanup-aware interruption, matching the runner's owned-process behavior.

The final M8 integration review found two existing runner edges affecting the GPU handoff: a completed experiment could be marked aborted if resumed after its old deadline, and a long agreement pass could exceed the remaining budget before the next guard. Completed resume is now an immediate no-op; agreement has a cancellation deadline, and startup readiness is bounded by remaining time. Focused tests cover the completed/deadline and hanging-agreement cases. These are prerequisite correctness fixes for the requested M8 end-to-end handoff, not changes to statistical thresholds or the experiment design.

Adding goodput to the shared M8 analysis also requires explicitly classifying it as higher-is-better in both comparisons and A/A splits. A focused test prevents a naming-based latency default from misclassifying this newly exposed rate metric.

### M9 prerequisite — detached automation

The owner requested a campaign that continues if the assistant's usage allowance
runs out. A stdlib Python launcher starts a new process session on the GPU host,
with detached stdin and persistent log files; no assistant, tmux, or scheduler
service is needed after launch. A fresh state directory and inherited file lock
preserve one job record, while the runner's database lock still excludes conflicting
execution. Progress is atomically replaced and keeps the experiment ID, stages,
exit codes, deadline and backup failures. Code 1 from regress is a finding and
permits subsequent reporting; other stage errors remain failures.

The required max-hours cap bounds the whole automation workflow and is passed to
the runner for a fresh experiment. Graceful cleanup and a bounded final backup can
extend past that deadline. Resume preserves the runner's original budget. Optional
hourly backups invoke the existing WAL-safe backup script with noninteractive SSH;
without a destination, results are retained only on the GPU machine. No cloud
credentials, rental shutdown, reboot recovery or automatic assistant wake-up are
implied. Live execution is not run (needs GPU); process detachment, deadline aborts,
terminal statuses and report-stage continuation are tested using an explicitly fake
CLI, in addition to the existing full fake campaign tests.

### 2026-11-24 — owner-selected GPT-OSS live validation

The owner explicitly supplied SSH access and instructed execution against the installed GPT-OSS-120B model. This supersedes the offline-only session restriction and Qwen-first gate for this specific serving validation; it does not mark M9 Qwen complete. The actual host has one A100-SXM4-80GB, vLLM 0.32.0, Torch 2.13.0+cu130, an existing GPT-OSS MXFP4 server using Triton attention and Marlin MoE, and an advertised 8192-token context. Its startup log reports max_num_seqs=1. Client concurrency 8/32 therefore measures queueing behind a serialized server, not effective batching. No server restart, context-limit search or configuration-speedup claim is authorized or inferred.

A separate BenchmarkEndpoint type allows model-agnostic benchmark argv without weakening the Qwen ConfigSpec launch constraints. The separate existing-server script never starts or stops the external server. It records observation time explicitly rather than inventing startup time, checkpoints five reps per chat/RAG concurrency point at 1/8/32, uses a three-hour cap, and reports rep-level CIs with single-lifetime limitations. Version-specific help is checked before invocation; no Torch/vLLM upgrades or dependency replacements were made. A real three-request/four-output-token smoke fixture from vLLM 0.32 passed the raw-derived metric cross-check, including direct E2E latency consistency. It does not replace all provisional 0.15.1 fixtures or establish quality compatibility.

Supervisor manages the new benchmark worker with autorestart disabled and persistent logs, leaving the existing template services alone. Dataset measurements are raw synthetic completions, not a chat-template/reasoning-quality evaluation. Independent launch noise, quality comparisons, 32k/64k/128k context and the Qwen campaign remain not run (needs GPU). Recorded live results are labelled as live, not as offline selftest evidence.

### GPT-OSS validation completion

The owner-selected existing-server run finished normally in 108.4 minutes: all 30
reps and 3,000 requests passed fixed-length checks. The off-machine DB passed
integrity_check; every archived raw file was independently re-parsed through the
same adapter and metrics cross-check. The completed report preserves all five-rep
point CIs and labels the actual max_num_seqs=1 serialization limitation. Provider
instance label is redacted only in the public artifacts; original metadata, raw
arrays, DB, logs and deployed-source hash manifest remain in the local archive.
The captured base git SHA is supplemented by that hash manifest rather than being
misrepresented as the exact unmodified code checkout. The running template model
server and rental were not stopped or destroyed. Model quality, independent-launch
noise and context tuning remain outside this completed serving validation.
