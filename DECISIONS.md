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
