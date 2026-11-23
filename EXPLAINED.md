# Function explanations — M0

## Production wiring and environment

`cli.main` parses the two implemented subcommands and forwards them to their handlers.
Keeping this function limited to parsing and dispatch avoids business logic in the CLI.

`env.command_output` runs a command with a timeout and returns output or an explicit
failure record. It catches missing executables and timeouts so an offline machine
can still produce a useful environment report.

`env.package_version` reads an installed distribution's version without importing it.
An absent package returns null because absence is useful diagnostic information.

`env.host_ram_bytes` asks the operating system for physical memory size.
It falls back to macOS sysctl and returns null if neither method is available.

`env.torch_cuda_version` parses the literal CUDA version from torch's version file.
AST parsing reads data without executing package code or initializing GPU libraries.

`env.cpu_model` reads the CPU brand through macOS sysctl or Linux procfs.
Platform information supplies a fallback when those details are unavailable.

`env.snapshot` collects host information, package versions, GPU/driver output, Git
provenance, a dependency hash, and two selected instance variables. It keeps missing
values explicit and avoids recording arbitrary environment secrets.

`env.doctor` checks executable availability and any registered production flags,
then prints the environment report. Its return value is 3 for an environment failure
so callers can distinguish missing prerequisites from a usage error.

`env.selftest_stub` verifies that CLI dispatch reaches a handler.
It explicitly states that full pipeline verification is pending M6, so its success
cannot be mistaken for an experiment result.

## Fake HTTP server

`fake_vllm.delays` builds seeded prefill and token delay schedules, scaled by active
concurrency and injected slowdown. Computing the schedule separately makes jitter
and scaling testable without relying on noisy wall-clock measurements.

`fake_vllm.chunk` builds one completion or chat streaming event, including the final
finish event. Sharing the small builder keeps both endpoint formats consistent.

`fake_vllm.create_app` creates an isolated FastAPI application with its own active
request count and failure RNG. Separate instances prevent state leaking between tests.

`create_app.health` returns a successful readiness response.
It is deliberately cheap so subprocess tests can poll it during startup.

`create_app.models` advertises the configured fake model using the models-list shape.
This lets callers test readiness and served-name validation independently of generation.

`create_app.respond` validates the model, applies failure/hang injection, and builds
streamed or ordinary output. Both routes share this logic to apply identical delay
and failure semantics.

`respond.tokens` increments active generation count, sleeps through the seeded
schedule, and yields token indices. Its finally block restores the count even when
iteration is cancelled or the consumer disconnects.

`respond.events` converts generated tokens into SSE messages and finishes with DONE.
It yields incrementally so the network test exercises a real streaming response.

`create_app.completions` forwards validated text-completion requests to the shared
responder. Keeping this route thin prevents endpoint-specific timing drift.

`create_app.chat_completions` forwards validated chat requests to the shared responder.
The chat switch changes the response format while preserving the same latency model.

## Fake executable

`command.add_flags` registers provisional flags from the shared constants file.
It distinguishes switches from valued arguments without copying their spellings.

`command.bench` produces seeded synthetic detailed arrays and matching summary fields,
optionally writing JSON. It exists only as an offline subprocess fixture producer;
it never claims to measure server capacity or generate real load.

`command.serve` prepares settings and provisional startup messages, starts one child,
and runs the fake HTTP app. Owning a real child makes teardown behavior observable
in subprocess tests without requiring a GPU engine.

`serve.stop_child` terminates and waits for the child, escalating to kill if needed.
Waiting reaps the child and makes PID disappearance a meaningful test assertion.

`serve.terminate` stops the owned child and exits on SIGTERM or SIGINT.
Registering this handler before uvicorn lets cleanup survive normal signal shutdown.

`command.main` parses the fake serve and bench command trees and dispatches execution.
Unknown arguments are rejected so tests can expose interface mistakes.

## Test helpers and tests

`test_executable.fake_env` prepends the current interpreter directory and fake binary
directory to PATH. It ensures subprocess tests run the installed package's interpreter
and cannot accidentally invoke a real vLLM binary.

`test_executable.test_cli` checks installed CLI dispatch and its usage-error code.
It asserts the selftest's explicit limitation instead of interpreting it as a full pipeline.

`test_executable.test_fake_bench` compares generated stdout, saved JSON, and a repeated
seeded invocation. This checks detailed array alignment and deterministic file output.

`test_executable.test_fake_start_stream_and_sigterm` launches the fake executable,
polls readiness, consumes a stream, and signals the parent. It verifies the child PID
vanishes and uses process-group cleanup if any assertion fails.

`test_executable.test_fake_startup_failure` runs the crash injection path.
It checks both the nonzero exit and the diagnostic message so an unrelated import
failure cannot masquerade as the intended crash.

`test_env.test_missing_doctor` removes executable availability and simulates absent GPU
tooling. It asserts a structured missing-vLLM message and environment-failure code.

`test_env.test_successful_doctor` supplies available fake prerequisites.
It checks success reporting without contacting or executing any real GPU software.

`test_env.test_command_failures` exercises a missing executable and an unsuccessful
command. These are separate failure modes the offline diagnostic wrapper must handle.

`test_env.test_timeout` substitutes a subprocess timeout.
It verifies the wrapper returns an unavailable result instead of raising to the CLI.

`test_timeout.timeout` raises a controlled TimeoutExpired exception.
This avoids wasting fifteen seconds or depending on a platform-specific sleeping command.

`test_env.test_snapshot_does_not_capture_secrets` adds a secret and one permitted
instance variable while replacing external commands. It asserts only the permitted
variable is stored and the dependency fingerprint is a hash.

`test_env.test_cuda_version_without_import` supplies a version file containing a
literal and an exception. Successful extraction proves reading the version does
not execute that exception or initialize torch.

`Distribution.locate_file` points the metadata stub at the temporary version file.
This isolates the version-reader test from whether torch is installed locally.

`test_fake.test_delay_model` checks same-seed reproducibility and arithmetic scaling
for slowdown, prompt length, and concurrency. Exact schedule assertions avoid timing
flakiness from operating-system scheduling.

`test_fake.test_endpoints` parametrizes both endpoint types and streaming modes.
It checks metadata, terminal stream events, token usage, validation, and active-count cleanup.

`test_endpoints.exercise` sends requests through the ASGI app with an asynchronous client.
Running this coroutine with asyncio.run avoids adding a pytest async plugin dependency.

`test_fake.test_injected_failure_and_hang` checks deliberate HTTP errors and cancellable
hangs. It also verifies neither path leaves a generation counted as active.

`test_injected_failure_and_hang.exercise` drives both injected outcomes with a short
async timeout. This makes the hang test bounded without changing its intended behavior.

`test_fake.test_stream_applies_seeded_slowdown` records sleeps from actual streaming
request handling at baseline and at a 20% slowdown. It verifies the handler uses the
latency model rather than merely unit-testing a disconnected helper.

`test_stream_applies_seeded_slowdown.record_sleep` records each requested sleep duration.
It replaces only the clock wait so the test can compare exact scaling cheaply.

`test_stream_applies_seeded_slowdown.exercise` consumes a streaming request for supplied
settings. It keeps both comparison runs identical apart from the injected slowdown.

# M1 additions and changed functions

`ConfigSpec.valid_combination` checks the variant's model and quantization pair,
then the token-budget constraints. It rejects contradictory requests before any
server command can be assembled.

`ConfigSpec.argv` converts a validated configuration into a subprocess argument
list using the central mapping. Both prefix caching and chunked prefill are
explicit in either direction so engine defaults cannot silently choose them.

`WorkloadSpec.valid_workload` checks positive, unique concurrency and consistent
prefix dataset fields. Those checks prevent ambiguous point labels and malformed
synthetic workloads before calibration lookup.

`Factors.unique_levels` rejects empty or duplicate factor lists.
Each OFAT candidate therefore represents a distinct requested change.

`Calibration.positive_reps` rejects nonpositive point durations.
Nonfinite values are already rejected by the common model configuration so an
estimate cannot hide NaN or infinite costs.

`ExperimentSpec.valid_experiment` verifies the reference baseline, workload names
and context sizes, calibration coverage, and optional probe evidence. It also
rejects misspelled probe keys rather than quietly ignoring hardware evidence.

`planner.changed_config` merges one update into a baseline and validates the
result again. Pydantic model_copy can bypass validation, so this uses full validation.

`planner.probe_for` reads support status and evidence for one requested factor.
Missing evidence returns pending so planning never implies a successful live probe.

`planner.configurations` creates baseline, OFAT, deferred combined, and eager
regression records. Weight identity fields move together as one conceptual factor;
unsupported records keep their evidence for reporting.

`planner.points` creates each workload/concurrency point and its five stored rep
seeds. It computes point cost from calibration with proportional warmup reserve,
using a separate seeded RNG so schedule changes do not change prompt seeds.

`planner.make_plan` randomizes supported/pending OFAT entries and inserts the three
baseline launches at exact bookends and midpoint. It totals costs and records
probes, deferred selection, and unknown open-loop runtime as explicit limitations.

`plan_commands.plan_json` serializes a plan with sorted keys and a final newline.
No timestamps or paths are inserted, so identical input produces identical bytes.

`plan_commands.print_schedule` prints launch order, calibration costs, budget, and
limitations. A budget override changes the preview cap without editing the plan.

`plan_commands.plan_command` reads YAML, validates it, builds a plan, and writes JSON.
It converts configuration and filesystem errors into the specified usage-error code.

`plan_commands.run_command` provides a read-only dry-run of a serialized plan.
It reconstructs derived fields to reject tampering and explicitly refuses live
execution until M6 implements orchestration.

`env.check_flags` requests complete help for each currently used vLLM command and
extracts option names. It returns immediately on an unavailable help command or
missing flags so a mismatched interface cannot be treated as compatible.

`env.doctor` now checks the selected executable's pinned version and complete help
in addition to prerequisites and snapshot information. This versioned check is
still an environment diagnostic and never starts a real serving process.

`cli.main` now wires plan and run arguments to separate handlers.
Filesystem access and planning logic remain outside argument parsing.

`command.add_flags` can now omit one option through the fake-only environment
control. The missing option disappears from actual generated help, allowing a
real subprocess test of doctor's mismatch handling.

`command.main` now prints the fake's interface version and accepts full-help mode.
It translates that mode to argparse's ordinary help without importing real vLLM.

`tests.conftest.example` loads a fresh example dictionary for each test.
Tests can modify it to construct invalid input without sharing mutable state.

`test_config.test_explicit_flags` compares baseline argv against a complete worked
argument list and checks opposite boolean flags. This catches omitted defaults
and incorrect boolean direction mapping.

`test_config.test_variant_mapping` checks all four weight identities and quantization
arguments. It verifies that model name and quantization move together consistently.

`test_config.test_invalid_server_config` parametrizes bad model pairs, memory,
token budgets, ports, and unknown keys. Matching validation messages ensures users
get meaningful configuration errors rather than later subprocess failures.

`test_config.test_invalid_workload` tests invalid concurrency and prefix fields.
These errors would otherwise create duplicate points or an incoherent dataset.

`test_config.test_example_validation` verifies the committed example parses and
retains the intended shared prefix length. This makes the quickstart example part
of the tested interface.

`test_config.test_invalid_experiment` constructs missing calibration, duplicate
levels/workloads, unprobed optional factors, invalid baseline/lengths, and bad costs.
It checks each rejects clearly without weakening the fixed five-rep requirement.

`test_planner.test_deterministic_plan_and_ofat` compares serialized hashes, roundtrips
the plan, and inspects each candidate's changed fields. It also verifies that the
combined configuration is unresolved rather than invented.

`test_planner.test_schedule_baseline_positions_and_dependencies` checks exact baseline
indices for full and reduced factor sets. It ensures combined selection follows
every OFAT candidate and baseline launch ordinals stay distinct.

`test_planner.test_seed_changes_order_but_not_membership` compares plans from two
experiment seeds. It checks that randomization changes ordering and request seeds
without changing which configurations are tested.

`test_seed_changes_order_but_not_membership.labels` extracts ordered configuration
labels for comparison. A named helper keeps the ordering assertion readable.

`test_planner.test_hand_computed_estimate_and_stored_seeds` checks the documented
1722-second launch and 21264-second total arithmetic. It also checks all launches
carry eight points and five comparable stored seeds per point.

`test_planner.test_budget_and_unsupported_probe_visible` constructs a budget overrun
and an unsupported checkpoint. It verifies that evidence stays visible while the
unsupported configuration gets no scheduled launch.

`test_planner.test_optional_factor_probe` supplies evidence for disabled chunked
prefill. It confirms the optional OFAT configuration is then included in the plan.

`test_planner.test_failed_baseline_probe` supplies a failed baseline load result.
It checks planning refuses an experiment without a usable reference configuration.

`test_planning_cli.test_plan_and_dry_run` runs the installed CLI twice, compares file
hashes, and checks costs and an overridden budget. It also proves the command
refuses execution without dry-run before a runner exists.

`test_planning_cli.test_missing_config_errors` requests a nonexistent YAML file.
It checks the CLI returns usage-error code 2 and does not leave a misleading plan.

`test_planning_cli.test_invalid_dry_run_budget` supplies zero, negative, infinite,
and NaN budget overrides. These cannot become valid wall-clock campaign limits.

`test_planning_cli.test_tampered_plan_rejected` removes a launch from a saved plan.
It checks reconstruction catches derived data that no longer matches its experiment.

`test_planning_cli.test_fake_help_and_missing_flag` executes the fake's real help
and then hides a negative boolean option. Exact error comparison catches accidental
substring matches with the corresponding positive flag.

`test_planning_cli.test_doctor_with_fake_help` runs doctor using the actual fake
binary while stubbing hardware availability. It checks success and missing-option
failure without implying any real GPU or vLLM validation.

`test_planning_cli.test_wrong_version_and_help_failure` simulates an incompatible
version and unavailable help output. It verifies both produce actionable diagnostics.

`test_env.test_successful_doctor` now supplies matching version and help in its
existing success mock. The intended success behavior is unchanged; M1 introduces
new prerequisites that this mock must satisfy.

# M2 statistics engine

`stats._values` copies observations and rejects insufficient, nonnumeric, or
nonfinite data. Central validation keeps public functions consistent and prevents
silently removing failed measurements from a statistical result.

`stats._count` checks integer counts and their lower bound.
Booleans are excluded even though Python treats them as integers, because a
request for True bootstrap draws is almost certainly a caller mistake.

`stats._probability` validates an open-interval probability.
Confidence, alpha, and power cannot have endpoint values that make normal
quantiles infinite or intervals undefined.

`stats.mean` computes the arithmetic mean with an accurate floating-point sum.
It accepts an iterable so callers can aggregate launch observations without
building additional data structures themselves.

`stats.percentile` sorts observations and applies linear/type-7 interpolation.
A convex weighted sum avoids subtracting opposite-sign large numbers solely
to interpolate between them.

`stats.median` delegates to the 50th percentile.
This gives odd and even sample sizes the same documented interpolation rule.

`stats.standard_deviation` computes sample SD with denominator n-1.
At least two observations are required because one observation cannot estimate
sample variability.

`stats.coefficient_of_variation` divides sample SD by the absolute mean.
Its result is dimensionless and it rejects a zero mean instead of inventing
an infinite or zero relative variability.

`stats.bootstrap_ci` repeatedly resamples scalar rep-level observations and
returns percentile bounds on their mean. A local RNG makes runs reproducible
without changing application-wide random state or treating requests as independent reps.

`stats.permutation_test` compares absolute differences of group means over
all feasible label assignments or seeded random assignments. It records which
method/count was used and adds one to Monte Carlo counts so simulation cannot
produce a spuriously zero p-value.

`stats.holm_adjust` sorts a family of p-values, applies decreasing family-size
multipliers, and takes their running maximum. It returns adjusted probabilities
in the original order so callers can associate each result with the correct metric.

`stats.wilson_interval` computes a two-sided Wilson score interval for a proportion.
It validates integer counts and keeps rounding at the boundaries inside [0,1].

`stats.mcnemar_exact` computes a paired binary comparison from the two discordant
counts using an exact binomial tail. Integer combinations delay floating-point
rounding until the final probability ratio.

`stats.minimum_detectable_effect` estimates within-launch and between-launch
variance, then the normal-approximation percent shift for the requested design.
Keeping candidate-launch noise in its standard error prevents extra reps within
one launch from creating an artificial claim of high power.

# M2 tests

`test_percentile_worked_arrays` checks fixed arrays against hand-computed type-7
percentiles, including endpoints, ties, negative values, and large opposite signs.
The expected values do not depend on importing NumPy or calling the implementation.

`test_descriptive_worked_values` checks mean, median, sample SD, and CV on simple
worked data. It also checks constant data and cancellation to verify numerical
behavior beyond a single happy-path example.

`test_bootstrap_worked_seed_and_reproducibility` checks a tiny seeded draw sequence
whose resampled means can be calculated by hand. It also exercises the default
10,000-resample interval and constant observations.

`test_resampling_does_not_mutate_global_rng_or_inputs` compares global RNG state
and input values around both resampling algorithms. Constant data provide the
independently known interval and p-value while checking those side effects.

`test_exact_permutation_enumerated_by_hand` enumerates the six two-versus-two
assignments explicitly in comments. Shift, tiny-scale, duplicate, and group-swap
checks ensure tie handling does not change the mathematical comparison.

`test_monte_carlo_worked_draws` records six fixed sampled assignments and their
two extreme statistics. It verifies the conservative 3/7 p-value, reproducibility,
and the positive correction when no simulated assignment is extreme.

`test_permutation_default_method_boundary` checks combination counts on both
sides of the 20,000-assignment cutoff. Tied inputs make p=1 known by hand while
confirming that the default Monte Carlo branch performs 100,000 draws.

`test_holm_worked_example` checks a sorted/multiplied/running-maximum correction
and restoration of original order. It also checks ties, clipping, and an empty family.

`test_wilson_worked_values` checks the score formula on a balanced binomial sample
and zero/all-success boundaries. A confidence level with z=1 supplies an additional
closed-form interval independent of the default z value.

`test_mcnemar_worked_tables` checks exact discordance tails from constructed 2x2
tables, including no differences and symmetry. Large balanced counts verify the
integer-ratio computation does not overflow from early conversion to floats.

`test_mde_balanced_worked_components` checks each variance component, standard error,
and percent MDE against the documented three-launch example. It also checks the
result retains sample counts and the requested alpha/power.

`test_mde_unbalanced_worked_components` derives the effective replication and
variance terms for launch sizes two, three, and two. It catches the mistake of
using a balanced-design formula after a partial or interrupted launch.

`test_mde_zero_clipping_scaling_and_replication` checks nonnegative variance
truncation, constant data, scale invariance, and changes in replication. It
specifically verifies that extra candidate reps cannot remove between-launch noise.

`test_invalid_observations` rejects empty, nonfinite, string, and boolean data.
No bad measurement should silently vanish or be coerced into a valid numeric sample.

`test_invalid_percentiles` rejects probabilities outside the percentile scale
and nonnumeric/nonfinite values. These inputs cannot refer to a valid interpolation.

`test_insufficient_data_and_zero_mean` checks minimum sample sizes and the undefined
zero-mean CV. It ensures a result is not returned when its variance or denominator
cannot be estimated from the supplied data.

`test_invalid_bootstrap_parameters` checks confidence, counts, and seeds.
Invalid settings must fail before consuming random draws or allocating resamples.

`test_invalid_permutation_parameters` checks the enumeration limit, Monte Carlo
count, and seed. This avoids silently changing a requested statistical method
because of an invalid loop bound.

`test_invalid_holm_probabilities` rejects p-values outside [0,1] or without a
finite numeric value. A malformed test cannot silently enter a correction family.

`test_invalid_wilson_inputs` rejects inconsistent counts and invalid confidence.
The score interval is defined only for an actual binomial count and positive n.

`test_invalid_mcnemar_counts` rejects negative, fractional, and boolean discordances.
The exact binomial calculation requires nonnegative integer paired counts.

`test_invalid_mde_inputs` checks independent-launch and within-launch replication,
finite inputs, nonzero mean, and valid planning settings. It prevents a numerical
MDE from masking a design that cannot estimate its own noise.

`test_source_has_no_numpy_imports` parses every Python module under src and
inspects its import statements. This enforces the project's no-NumPy library
constraint without installing NumPy or relying on a fragile text match.
