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

# M3 server lifecycle, probes, and changed wiring

`env.vllm_errors` extracts the existing binary/version/full-help validation into
a reusable function. Doctor and ServerManager now share the same contract checks
instead of maintaining slightly different notions of compatibility.

`env.doctor` uses that shared validation before its existing environment report.
Its output and exit-code contract remain unchanged while preflight can reuse it.

`env.gpu_memory_used` queries one visible GPU and parses numeric used memory in MiB.
Missing tools, ambiguous multi-GPU output, and invalid numbers cause refusal
because unknown memory use cannot establish a safe launch.

`env.vllm_processes` identifies serving executables, Python vLLM modules, and worker
names in read-only process output. It returns only PIDs and executable names so
an existing server's arguments cannot leak an API key into a launch error.

`env.process_group_active` checks group IDs and process states through read-only ps.
It treats only zombies as inactive because they cannot run or retain GPU allocations,
and unknown inspection output fails rather than being interpreted as a clean exit.

`ServerTimeouts.__post_init__` checks every configured deadline and poll interval.
Rejecting nonfinite or nonpositive values prevents unbounded or busy-loop lifecycle waits.

`server.parse_resolved_config` extracts observed engine settings from provisional
startup log shapes while retaining raw matched lines. Later values override earlier
ones, and missing values are not filled from requested flags.

`server.log_tail` reads only the last 200 lines into a bounded deque.
It makes startup failures inspectable without placing an entire long log in a result.

`server.preflight` checks port availability, memory, other serving processes, and
version/flag compatibility. It never signals discovered processes, and its refusal
messages tell the owner how to handle an image's auto-launched server.

`ServerManager.__init__` records the binary, log directory, timeouts, and initially
empty ownership state. A manager without a successful Popen has no group it can signal.

`ServerManager.start` creates an exclusive log, validates safety, launches in a
new process group, and waits for readiness. It records startup results and attempts
cleanup on failure or interruption, preserving a failed cleanup gate for the next start.

`ServerManager._wait_ready` polls both health and the advertised model list within
a bounded deadline. It requires the expected model and an owned process that is
still alive, rather than accepting any process answering the same port.

`ServerManager._signal_group` sends a signal only to the remembered owned group.
If a permission error races with exit, it suppresses the error only after separate
read-only inspection confirms the group no longer has an active member.

`ServerManager._group_exists` checks the owned group through process-state inspection.
It avoids using signal zero as a potentially permission-sensitive existence probe.

`ServerManager._wait_exit` polls/reaps the direct parent and checks for active group
members until a deadline. Reaping the parent prevents its own zombie from keeping
a normal cleanup waiting unnecessarily.

`ServerManager._wait_gpu` polls memory until it is below the idle threshold or the
release timeout expires. It keeps the pending flag set on errors so an unsafe
next launch cannot quietly proceed.

`ServerManager.stop` sends TERM and, if needed, KILL to the owned group before
closing logs and checking GPU release. It is idempotent on completed cleanup and
records/raises cleanup failures without forgetting ownership.

`probe.probe_specs` builds validated configurations for weights, both chunked-prefill
directions, or FP8 KV cache. Invalid model/variant combinations fail before any process starts.

`probe.run_probe` executes and tears down each probe, preserving requested settings
and complete launch results. It compares actual resolved optional-factor values and
halts additional probes after cleanup failure instead of claiming support.

`probe.probe_command` validates CLI input, runs probes, and writes an exclusive JSON
result file. It reports configuration errors separately from unsuccessful probes and
never overwrites existing output or silently edits an experiment plan.

`cli.main` wires the probe options to the new handler.
The CLI still does not contain lifecycle, hardware, or parsing logic.

`command.serve` now emits additional provisional KV/backend/graph settings and
supports startup hangs, unhealthy responses, wrong models, and ignored chunk flags.
These controls exercise lifecycle failures without importing or running real vLLM.

`create_app.health` can now return the fake's configured unhealthy response.
Its default remains healthy so earlier fake-server behavior and tests remain intact.

# M3 unit tests

`test_resolved_config_provisional_fixture` checks every supported resolved field
against a constructed full startup log. It also checks matched raw lines and the
provisional marker remain attached for later replacement with real evidence.

`test_log_overrides_unknown_fields_and_ansi` checks later overrides and colored log
matching. It ensures absent fields remain absent rather than being invented from a request.

`test_tail_is_last_200_lines` checks the exact retained range of a 300-line file.
It also checks a missing log yields an empty tail without masking the main failure.

`test_timeout_validation` rejects zero, negative, nonfinite, and boolean timing values.
These cannot represent a meaningful bounded lifecycle wait.

`test_gpu_query_rejects_unknown_or_multiple_gpus` supplies malformed or ambiguous
GPU memory output. A successful subprocess exit alone must not make unknown memory safe.

`test_unavailable_safety_tools` simulates a failed system command.
It verifies memory, process discovery, and group-exit inspection all fail closed.

`test_process_scan_matches_executables_not_mentions` mixes serving processes with
unrelated tests, shell text, and Python arguments containing vllm. It verifies
only executable/module identities are treated as existing servers.

`test_sigkill_escalation_and_owned_group_only` simulates a group that outlives TERM.
It checks KILL targets that same owned group and an idempotent stop sends no further signals.

`test_cleanup_failure_retains_ownership` simulates a group still active after KILL.
It checks the failure remains recorded and ownership is retained for a later cleanup attempt.

`test_process_scan_failure_and_secret_redaction` supplies an existing server with an
API-key argument, then malformed ps output. It verifies diagnostics omit arguments
and malformed inspection does not get interpreted as no existing server.

`test_group_state_uses_read_only_inspection` supplies active, zombie, and missing
group IDs in process output. It verifies only active members keep a group pending cleanup.

`test_live_permission_failure_is_not_ignored` simulates a denied signal against a
still-live group. It checks stop raises and retains the next-launch gate.

`test_live_permission_failure_is_not_ignored.denied` raises a controlled permission error.
The test can verify refusal without attempting to signal any real process group.

`test_exited_group_permission_race_is_verified` simulates exit between inspection
and a failed signal. It requires a second inspection before accepting that cleanup is safe.

`test_exited_group_permission_race_is_verified.denied_after_exit` raises the signal
error during that simulated race. The parent test controls process-state inspection
independently rather than suppressing all permission errors.

`test_probe_variant_spec` checks each published model/quantization mapping used by probes.
It ensures a requested weight variant is not silently replaced with baseline weights.

`test_optional_probe_specs` checks both boolean chunk probes and the FP8 KV request.
It also rejects an unknown variant before reaching a server manager.

`test_cleanup_failure_preserves_evidence_and_stops_following_probes` injects cleanup
failure into a probe manager. It checks the evidence survives, no further launch starts,
and an empty probe set cannot be labeled supported.

`test_invalid_or_existing_probe_output_never_starts` supplies an invalid model and an
already existing output path. It checks both refuse before creating a manager and keep
the existing file unchanged.

# M3 integration fixtures and tests

`fake_machine` places fake NVIDIA/preflight-process commands ahead of the real PATH.
Group-exit inspection still delegates to the actual OS ps so child cleanup is tested
against real subprocesses rather than a fake absence result.

`spec` allocates an ephemeral local port and returns a validated baseline configuration.
Tests avoid hardcoded shared ports that could conflict with other development services.

`manager` creates a fake-binary manager with per-test logs and short bounded waits.
This exercises the production lifecycle code while keeping failure tests quick and offline.

`test_start_readiness_resolved_and_child_tree` launches the fake, reads resolved values,
and verifies the child exists. After stopping, it checks the child is gone and lifecycle
timestamps and cleanup state are recorded.

`test_port_busy_never_signals_external_process` occupies the requested port while an
unrelated process is alive. It checks refusal sends no group signal and the unrelated
process survives.

`test_gpu_busy_refuses_and_stop_before_start_is_safe` supplies the exact idle-threshold
memory usage through the fake NVIDIA executable. It verifies no process starts or receives
a signal, including an initial stop on an unused manager.

`test_existing_vllm_process_is_not_killed` advertises an existing process as a server.
It checks refusal leaves that process alive instead of attempting to free the GPU itself.

`test_startup_crash_tail_and_probe_classification` injects an OOM-shaped startup failure
with more than 200 diagnostic lines. It checks ordinary versus load-probe statuses and the
exact bounded tail retained in the error.

`test_readiness_failure_cleans_child` exercises a startup hang, unhealthy health endpoint,
and wrong advertised model. All three must time out and finish owned-process cleanup.

`test_gpu_release_timeout_blocks_next_launch` changes fake memory to busy after readiness.
It checks timeout prevents a new launch, then confirms an explicit stop can finish once
the simulated memory condition clears.

`test_factor_probe_records_honored_and_ignored_flags` runs both chunk directions, then
repeats with the fake forcing chunked prefill on. It checks the ignored flag is recorded
as not honored with both requested and observed values preserved.

`test_probe_cli_saves_evidence` invokes the installed CLI against the fake binary.
It verifies successful JSON evidence includes the completed cleanup state.

`test_duplicate_launch_id_does_not_overwrite` reuses an already recorded launch ID.
It checks refusal preserves every byte of the original log rather than destroying provenance.

`test_missing_flag_refuses_before_spawn` hides a required option from the fake help.
It checks preflight fails before ownership or server startup is established.

`test_spawn_error_never_signals_unowned_group` makes Popen fail after preflight.
It checks no group signal is sent when no owned child was successfully returned.

`test_spawn_error_never_signals_unowned_group.fail_spawn` raises a controlled OS spawn
failure. This isolates the ownership boundary without needing an unreliable real OS fault.

`test_active_launch_cannot_be_replaced` attempts another start while a server is ready.
It checks the original launch record stays current until explicit cleanup finishes.

`test_probe_cli_failure_keeps_log_evidence` runs an injected crash through the CLI.
It checks exit 3 still writes per-launch unsupported status and startup diagnostics to JSON.

`test_invalid_launch_id_is_rejected` supplies a path-traversal-shaped launch ID.
It verifies the identifier is refused before a group can be created or a log written outside its directory.

`test_interrupted_start_cleans_owned_process` raises KeyboardInterrupt after actual readiness.
It checks the interrupt propagates while the launch records aborted and completes cleanup.

`test_interrupted_start_cleans_owned_process.interrupt_after_ready` waits for the real
fake-server readiness path before raising. This ensures the interruption test owns an actual
server/child tree rather than only simulating ownership metadata.

# M4 adapter, metric models, and fake changes

`LoadSpec.valid_load` requires exactly a concurrency cap for closed mode or an
arrival rate for open mode. Keeping these modes exclusive prevents a capped
capacity measurement from being mislabeled as open-loop latency.

`DetailedResult.aligned_requests` checks consumed arrays against the declared
prompt count and tool outcome counters. It rejects contradictory raw records
rather than guessing which samples succeeded or silently dropping missing data.

`RequestResult.success` defines transport success from the absence of a recorded
error. Output-length validity is checked later so a successful zero/short output
can still be reported as truncated.

`loadgen.build_command` maps validated server/workload/load/SLO data to an argument
list through the central flag vocabulary. It sets fixed generation and detailed
metrics explicitly and performs no process or filesystem I/O.

`loadgen.parse_result` validates the pinned JSON fields used by the adapter and
preserves their raw request values. It wraps schema failures in AdapterBrokenError
so future orchestration cannot confuse parsing corruption with a server regression.

`RepMetrics.can_compare` exposes the documented ok-versus-partial/failed gate.
Downstream capacity and regression code can use this gate without reimplementing
the failure-percentage threshold.

`metrics.e2e_seconds` reconstructs end-to-end time from TTFT plus observed gaps.
The pinned serializer lacks raw E2E, so this derived value is provisional and its
p99 is checked against the tool rather than treated as an independent observation.

`metrics.tpot_seconds` divides total observed decode time by output_tokens-1.
It does not divide by stream-gap count because chunks may bundle tokens, and it
returns None when no token-to-token denominator exists.

`metrics.distribution` converts seconds to milliseconds and uses stats.py for
means and percentiles. It includes observation count and leaves empty statistics
missing rather than presenting a zero latency without samples.

`metrics.cross_check` recomputes tool summaries from all transport successes and
checks the relative tolerance and exact token totals. Using the tool's population
here prevents expected truncation exclusions from looking like parser corruption.

`metrics.summarize` classifies output validity, derives full-length latency views,
and computes physical throughput and SLO goodput. It retains failure counts and
notes so excluded requests and reps remain visible to reports and comparisons.

`metrics.baseline_chat_capacity` averages comparable rep throughput within each
supplied baseline chat concurrency and chooses the largest point mean. It stores
the selected point/count and exclusions instead of choosing a single lucky rep.

`metrics.open_loop_loads` creates three finite-rate LoadSpecs from measured capacity.
It rejects absent/nonpositive capacity and omits any concurrency cap, leaving the
actual arrival process to the wrapped tool.

`command.add_flags` now recognizes benchmark switches and multi-value goodput pairs.
This allows the fake's real argparse/help interface to exercise the new command
builder and doctor checks without importing vLLM.

`command.fake_percentile` computes synthetic tool-summary percentiles independently
of the library's statistics implementation. Its simple interpolation avoids a
shared bug making an adapter cross-check pass itself.

`command.bench` now accepts workload/load flags and emits the consumed pinned result
schema with counts, timing arrays, and synthetic scheduling metadata. It supports
controlled failures and short outputs but never sends load or claims GPU capacity.

# M4 unit tests

`test_loadgen.worked_raw` loads a fresh independent three-request fixture.
Tests can corrupt fields without changing another test's reference artifact.

`test_exact_workload_point_commands` checks all eight configured closed-loop points
and three open-loop rates against complete argument snapshots. It verifies that
open-loop commands contain no hidden client concurrency cap.

`test_slo_arguments_and_custom_binary` checks the executable override and exact
three-part goodput arguments. This verifies both units and multi-value ordering
at the subprocess boundary.

`test_invalid_load` rejects missing, contradictory, nonpositive, nonfinite, and
coerced boolean/string load settings. These inputs cannot identify an unambiguous
closed- or open-loop experiment point.

`test_invalid_command_inputs` rejects invalid seeds, file names, unconfigured
closed points, and context overflow. The builder must reject them before a future
runner can execute an inconsistent command.

`test_parse_schema_and_bundled_stream_gaps` checks raw values and unequal stream-gap
counts without equating them to output tokens. It also verifies parsing leaves
the original artifact unchanged.

`test_invalid_result_is_adapter_broken` corrupts arrays, counts, required summaries,
timings, and backend identity. It requires an explicit adapter error rather than
coercion or a partially invented successful result.

`test_invalid_slo_thresholds` rejects nonnumeric, boolean, negative, and nonfinite
thresholds. These cannot be silently converted into meaningful millisecond SLOs.

`test_metrics.raw` loads the same hand-worked result independently for metric tests.
Its tool numbers are fixture constants rather than outputs generated by stats.py.

`test_metrics.simple_raw` constructs equal-timing request populations with controlled
transport, short, and long outcomes. The uniform 100ms TTFT/200ms E2E makes their
summary expectations arithmetic rather than another implementation of percentiles.

`test_hand_computed_distributions_rates_and_goodput` checks the full worked TTFT,
E2E, pooled ITL, per-request TPOT, throughput, and SLO calculation. Its comments
show why bundled chunks produce different pooled and per-request views.

`test_reconstruction_does_not_trust_nonexistent_pinned_e2e_array` supplies a bogus
legacy E2E field alongside correct pinned arrays. It proves this unexported field
cannot silently become another timing authority.

`test_crosscheck_more_than_one_percent_is_broken` perturbs each required tool summary
beyond the tolerance. It requires the failure to identify the mismatched metric.

`test_crosscheck_exact_one_percent_boundary` checks both directions at exactly 1%.
The stated greater-than rule must not become greater-than-or-equal through rounding.

`test_crosscheck_token_totals_are_exact` changes integer input/output totals by one.
Token accounting is an exact schema invariant rather than a relative-latency tolerance.

`test_failure_and_truncation_classification` tests exact 1%, partial, no-valid-output,
and overlong boundaries. It also checks the distributions' n and comparison notes
reflect the actual excluded population.

`test_truncated_outputs_do_not_meet_goodput_but_physical_tokens_count` checks a single
short output among 100 requests. Its worked totals separate delivered physical
throughput from valid full-length goodput without disguising either definition.

`test_one_token_and_empty_distributions_are_not_invented_zeros` checks single-token
TPOT and an all-failed rep. It requires empty statistics to remain missing while
applying the tool's zero-TPOT convention only to single-token goodput.

`test_zero_summary_must_match_zero_recomputed_rate` supplies nonzero reported
throughput when no output tokens exist. It verifies the relative-comparison rule
has a meaningful strict behavior at a zero denominator.

`test_measured_capacity_and_open_loop_rates` derives capacity from worked repeated
point measurements and excludes a partial rep. It checks the exact 50/80/95%
rates and verifies no concurrency limit appears in those LoadSpecs.

`test_measured_capacity_and_open_loop_rates.measured` produces a validated fixed-count
rep for a chosen worked throughput by setting its duration. It lets the parent test
control rate arithmetic without constructing an unverified RepMetrics by hand.

`test_invalid_capacity_or_metric_inputs` rejects absent/invalid capacity data and
invalid expected output lengths. A future runner cannot substitute a guessed zero
capacity or silently analyze a nonsensical generation target.

`test_zero_output_transport_success_counts_as_truncated` represents a successful
stream that produces no output tokens. It checks transport accounting stays correct
while the fixed-length result is rejected and counted visibly as truncated.

# M4 executable integration tests

`test_loadgen_pipeline.fake_path` selects the active virtualenv interpreter for the
fake executable. It avoids accidental dependence on a system Python or real vLLM.

`test_builder_fake_executable_parser_metrics` executes built commands for both dataset
families and load modes, parses saved JSON, and cross-checks derived metrics. It also
checks warmups stay outside measured arrays and repeated seeded output is deterministic.

`test_fake_failed_and_truncated_reps` drives independent request-failure and short-output
controls through the executable. It checks these artifacts become partial reps with
the correct separate failure counts.

`test_fake_benchmark_process_failure` injects a nonzero benchmark exit.
It verifies the failure diagnostic and absence of a misleading successful result file.

`test_doctor_checks_benchmark_options_too` hides a required benchmark-only option from
actual fake help output. It proves doctor's registration covers the new adapter
instead of only continuing to validate serve flags.

`test_overflowed_derived_rate_is_not_accepted_as_within_tolerance` supplies a finite
but impossibly small duration that overflows the derived throughput. It checks
that an infinite tolerance cannot make an invalid rate appear to cross-check successfully.

# M5 functions

`quality.quality_command` builds a pinned raw-completion gsm8k command with fixed
few-shot/seed settings. It validates subset size and model-argument delimiters
before any external command can run.

`quality.parse_samples` validates identities and binary correctness in logged
samples. Both filters must cover the same documents so pairing cannot silently
compare different evaluation subsets.

`quality.read_samples` reads JSONL and delegates all sample validation.
This keeps file access separate from the statistical comparison itself.

`quality.quality_summary` calculates per-filter accuracy and Wilson intervals.
It includes n and correct counts to make every reported proportion auditable.

`quality.paired_quality` aligns baseline and candidate documents by identity and
hash. Exact McNemar uses only discordant pairs, preserving the paired design.

`quality.fixed_prompts` returns the same 200 synthetic arithmetic prompts.
They test output stability and do not represent a broad quality benchmark.

`quality.agreement` compares token sequences and locates the first differing
position. Exact matches are excluded from the divergence average rather than
inventing a divergence at position zero.

`quality.greedy_outputs` requests integer token IDs from raw greedy completions.
It rejects decoded strings or incomplete usage so agreement cannot claim token
identity from ambiguous text.

`quality.agreement_check` manages an HTTP client for the running server and
optionally compares against saved reference outputs. It does not start a server.

`test_quality_command_snapshot` checks exact CLI arguments and subset defaults.
It verifies the command contract without installing the GPU-only harness extra.

`test_sample_parser_and_paired_worked_values` checks a 3/4 accuracy Wilson example
and b=3,c=0 McNemar p=.25. Hash and sample-set mismatches must fail pairing.

`test_agreement_worked_sequences` checks exact matches, internal divergence and
strict-prefix divergence. Its expected mean position is calculated by hand.

`test_reject_duplicate_and_incomplete_filters` checks sample identity integrity.
Malformed populations cannot turn into apparently paired quality evidence.

`test_fake_server_greedy_token_agreement` exercises actual fake HTTP handlers and
compares returned token IDs. The nested check coroutine avoids an async test-plugin dependency.

`test_agreement_rejects_decoded_text_instead_of_ids` supplies an invalid response
through MockTransport. Its nested handler and check coroutine ensure ambiguous
decoded text cannot be accepted as token IDs.

### M6 functions

`src/inferencepilot/store.py:encode` — Serialize JSON deterministically while rejecting non-finite numbers. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:__init__` — Initialize the component and validate the resources it owns. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:close` — Release the SQLite connection. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:meta` — Read a version or execution checkpoint by its exact key. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:set_meta` — Commit a version or checkpoint independently by key. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:rows` — Read validated table columns using parameter-bound values. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:insert` — Persist a validated row and assign its unique identity. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:update` — Persist changes to one identified row using parameter-bound values. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:checkpoint_rep` — Commit a rep and its logical checkpoint in a single transaction. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:artifact` — Provide the artifact operation for this module. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:create` — Persist the immutable plan, environment snapshot, and requested configurations. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/store.py:records` — Collect related experiment records through the store boundary. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:execute` — Bound a child command and reap its owned process group on interruption. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:__init__` — Initialize the component and validate the resources it owns. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:remaining` — Enforce the persisted wall-clock deadline before more work starts. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:run` — Execute or resume the stored randomized schedule under an exclusive database lock. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:launch` — Own one physical server lifetime and checkpoint its benchmark and quality work. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:point` — Invoke seeded benchmark reps and persist their raw artifacts and verified summaries. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/runner.py:check_quality` — Persist harness sample statistics and paired greedy token outputs. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/analysis.py:point_key` — Give closed and open points stable distinct comparison identities. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/analysis.py:observations` — Group comparable rep metrics by configuration, point, and physical launch. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/analysis.py:aggregate` — Compute mean-of-rep summaries with bootstrap intervals and replication counts. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/analysis.py:capacity` — Select measured baseline chat capacity with its contributing rep count. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/analysis.py:combined_spec` — Choose each observed OFAT level independently; validate interactions in its own launch. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/commands.py:run` — Execute or resume the stored randomized schedule under an exclusive database lock. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/commands.py:interrupt` — Convert SIGTERM into a cleanup-aware interruption. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/commands.py:database_command` — Dispatch database-oriented CLI operations outside argument parsing. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/commands.py:selftest` — Delegate offline validation to the fake package in a separate process. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/fakes/selftest.py:mini_plan` — Build a small seeded synthetic experiment on an available local port. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/fakes/selftest.py:fake_path` — Put explicitly fake binaries and the active Python environment on PATH. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/fakes/selftest.py:campaign` — Run and resume a synthetic campaign while checking complete rep counts. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/fakes/selftest.py:main` — Run the offline campaign and check its launch, quality, and agreement records. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/fakes/timing.py:delays` — Generate seeded synthetic prefill and per-token delays with concurrency scaling and optional slowdown. Returning a schedule keeps the fake benchmark independent of host sleep noise.


`cli.dispatch` wires argparse values to command handlers. `cli.main` turns configuration exceptions into a readable exit code 2, so CLI callers do not receive tracebacks for missing inputs.

### M7 functions

`src/inferencepilot/regress.py:verdict` — Provide the verdict operation for this module. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/regress.py:compare_family` — Apply Holm once across every available point and metric for one candidate. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/regress.py:cases_for` — Align baseline and candidate groups by workload, load point and metric, preserving physical launch groups. Missing arms remain in the test family so incomplete evidence cannot quietly reduce the correction.

`src/inferencepilot/regress.py:compare_experiment` — Compare each candidate with the requested baseline through the same family detector. Configuration identities remain attached to every row for transactional persistence and role-aware reporting.

`src/inferencepilot/regress.py:summary` — Count per-point verdicts and select the worst verdict in the documented order. Empty evidence is inconclusive rather than an automatic success.

`src/inferencepilot/regress.py:validate` — Leave out every physical baseline launch once; count both false directional findings. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/fakes/power.py:simulated_launch` — Collect five seeded synthetic timing observations over the fake HTTP endpoint with a shared launch effect. Separate seeds for launch drift and rep jitter exercise both sources of variation.

`src/inferencepilot/fakes/power.py:curve` — Repeat independent simulated campaigns at the four specified latency injections and run the unchanged detector. Count-backed detection rates and Wilson intervals report observed power without claiming real hardware performance.

`src/inferencepilot/fakes/power.py:main` — Run the offline campaign and check its launch, quality, and agreement records. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.


`stats.bootstrap_effect_ci` independently resamples baseline and candidate rep values and computes a percent effect for each draw. It uses the shared percentile definition and refuses zero or negative baseline values, where percent changes would be undefined or misleading.

`Store.replace_regressions` replaces one experiment's analysis in a single transaction. Re-running the detector therefore updates its evidence without duplicating old findings.

`commands.power` launches the explicitly fake power tool in a separate process. This keeps fake code outside production library imports.

`fake_vllm.timing` exposes only the fake scheduler's synthetic timing over HTTP. This makes repeated power experiments deterministic without pretending that host sleep timing measures GPU latency.

### M8 functions

`src/inferencepilot/recommend.py:dominates` — Compare throughput, E2E and quality using weak inequalities and require at least one strict improvement. Equal candidates therefore remain together in the Pareto set.

`src/inferencepilot/recommend.py:recommend` — Reject each candidate with specific evidence gaps or measured constraint excesses, then rank survivors by the declared objective. It accepts precomputed statistics so constraint decisions cannot change the underlying measurements.

`src/inferencepilot/recommend.py:valid` — Validate the objective point, supported latency metrics and quality filter before evaluating candidates. Rejecting ambiguous constraints prevents silently optimizing the wrong measurement.

`src/inferencepilot/report.py:prepare` — Collect stored records, compute shared aggregate/comparison evidence, run A/A validation and persist a recommendation. The returned bundle is the single numerical source for both report formats and plots.

`src/inferencepilot/report.py:number` — Refuse measurement formatting without an explicit positive observation count. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/report.py:markdown` — Render environment, requested/resolved settings, counted metrics, quality, comparisons and decisions as Markdown. Count-aware measurement formatting prevents isolated rates or percentiles from appearing without their sample size.

`src/inferencepilot/report.py:plots` — Optionally draw count-labelled throughput and p95 E2E evidence using matplotlib. Keeping this operation here makes ownership explicit and lets offline tests verify its behavior.

`src/inferencepilot/report.py:write` — Validate and write one evidence bundle to Markdown, JSON and optional plots. Rendering first prevents incomplete statistical output from being saved as an apparently finished report.

`src/inferencepilot/fakes/demo.py:main` — Run a fresh synthetic campaign and save its complete decision/report bundle under explicit output paths. It refuses a reused database to keep the demonstration evidence unambiguous.

`scripts/calibrate.py:calibrate` — Measure one baseline benchmark rep per configured point and retain raw results, startup and teardown durations. It writes a separate measured configuration so the illustrative calibration is never silently overwritten.

`scripts/calibrate.py:main` — Parse the owner-run calibration arguments and install a cleanup-aware SIGTERM handler. The helper must be invoked explicitly on the GPU host, while offline tests use fake binaries.


`analysis.recommendation_inputs` joins the stored config, resolved launch, paired quality and comparison evidence to shared aggregates. It passes uncertainty through to the recommender without computing another version of the statistics.

`fakes.selftest.synthetic_constraints` sets a generous SLO at the fake plan's only closed-loop point. It permits testing the whole decision/report path without implying that those limits describe real hardware.

The campaign wrapper defaults to a dry run and checks measured calibration and probe evidence before invoking the real CLI. The sync wrapper makes an integrity-checked SQLite backup first, then copies raw artifacts without deleting destination data, so active WAL writes are not lost.

`Runner.collect_agreement` wraps the HTTP agreement coroutine in the remaining experiment deadline and preserves the config seed. Cancellation closes the client before server teardown, so a slow quality pass cannot keep starting requests after the campaign budget is exhausted.

### Detached campaign automation

`scripts/detached_campaign.py:save_state` atomically replaces the progress JSON file. A reader after SSH reconnection therefore gets a complete checkpoint rather than a partial write.

`experiment_id` reads the latest committed experiment through a read-only connection. It tolerates the short period before the runner creates its database and never creates an empty database while polling.

`start` validates measured calibration, completed probes, runtime and destination paths before spawning a detached worker. Fresh state directories preserve previous logs, and inherited locking keeps the job record owned for the worker lifetime.

`Supervisor.__init__` restores job arguments and establishes a single supervision deadline. It keeps process ownership, checkpoint metadata and backup timing in one place.

`Supervisor.interrupt` records a stop request from SIGTERM or SIGINT. The polling loop then enters the same cleanup path used for deadline exhaustion.

`Supervisor.checkpoint` fills in the experiment identity when available and persists progress. Saved state makes later reconnection independent of the original assistant context.

`Supervisor.stop_child` signals only the process group the supervisor created. It permits the runner's owned-server cleanup before escalating, and records a warning if forced termination was needed.

`Supervisor.backup` invokes the existing consistent SQLite backup plus artifact transfer. It records failures without turning missing backup evidence into a successful backup claim.

`Supervisor.stage` runs one CLI stage with deadline monitoring and checkpoint updates. Allowed exit codes distinguish a regression finding from a command failure.

`Supervisor.run` sequences the campaign, analyses and report and always saves terminal status. It attempts a final configured backup so completed results can be collected later.

`main` wires start, status and the private worker entrypoint. The inherited lock stays open for the worker lifetime while user-facing errors retain exit code 2.

`store.latest_experiment_id` performs the detached supervisor's read-only polling through the store boundary. It tolerates an uncreated/initializing database and explicitly closes each connection, avoiding descriptor leaks during long jobs.

### Existing-server validation

`BenchmarkEndpoint` validates only the explicit loopback model, port and context limit needed by a benchmark. It has no server argv or tuning fields, so accepting GPT-OSS here does not relax Qwen experiment-launch invariants.

`scripts/benchmark_existing.py:endpoint` checks the current served model and advertised context through the model endpoint. Missing or unexpected identities fail before a benchmark can be labelled as that model.

`telemetry` captures read-only clock, power, temperature, utilization and memory information around each rep. It keeps diagnostics alongside measured data without changing GPU state.

`progress` atomically writes experiment identity and counted progress next to the DB. A reconnect can find the saved job without relying on chat context.

`render` uses shared analysis/statistics for counted rep means and confidence intervals. It explicitly limits findings to one observed server lifetime and synthetic raw completions.

`interrupt` converts stop signals into cleanup-aware interruption. The existing-server process is never signalled; only an owned benchmark subprocess is cleaned up.

`run` executes and checkpoints the selected workload points, enforcing a persisted creation-time budget and checking every result through the existing adapter. Resume skips committed logical reps and rejects changed options rather than relabelling a different experiment.

`main` validates the three-hour cap and acquires an exclusive external-campaign lock. This prevents duplicate benchmark workers from corrupting the intended load schedule.

### Offline live-readiness fixes

`env.gpu_telemetry` samples memory, clocks, power, temperature and utilization through the existing bounded command helper. It preserves timestamps, unavailable values and errors so diagnostics never invent zero readings.

`quality.evaluation_key` identifies the model/precision and fixed evaluation protocol eligible for reuse. Scheduling-only settings share evidence, while combined candidates include their full config and identity for independent validation.

`Store.checkpoint_quality` commits a measured result and its reusable source pointer in one transaction. A failed insertion cannot leave a cache entry referring to nonexistent evidence.

`Runner.evaluate_gsm8k` selects a valid saved source or performs a new harness evaluation, retaining paired comparisons and original sample lineage. Failed measurements never become reusable successes, and a committed first-baseline source can repair its interrupted reference-pointer update.

`report.evidence_scope` turns an explicit declaration and rep statuses into an accurate report label. It treats legacy provenance as unverified and avoids claiming successful live execution when no valid rep exists.

The runner now persists evidence declarations and full telemetry, and the report/recommender carry inherited quality source IDs. These changes retain the original statistical computations and make evidence reuse visible rather than silently increasing the apparent sample count.

### M9 pre-campaign pilot

`scripts/live_pilot.py:pilot` checks two greedy token-ID responses and a fixed first-N GSM8K subset against one owned baseline server. It saves timings, parsed quality, outputs and launch evidence, and always tears down its server so a broken quality path is found before the long campaign.

`scripts/live_pilot.py:main` parses the configuration and fresh artifact directory, then runs the pilot. Its SIGTERM handler allows normal owned-server cleanup when the supervising job is stopped.

`detached_campaign.Supervisor.run` now forwards an optional fixed quality subset to the runner. The runner persists that first-N protocol for resume and paired evaluation; omitting the option retains the full test split.

### README figures

`scripts/readme_figures.py:plot_results` plots the published GPT-OSS means and confidence intervals, with the original replication counts and single-sequence limitation visible. It reads saved statistics instead of recalculating them, and converts latency milliseconds to seconds only for display.

`scripts/readme_figures.py:plot_progress` draws observed rep and launch counts from a timestamped campaign snapshot. Each bar has its denominator and the figure states that count progress is not a completion-time estimate.

`scripts/readme_figures.py:main` rebuilds the two README PNGs from committed source files using the optional report dependency. It runs offline and leaves the GPU experiment untouched.

`analysis.combined_spec` now selects variant, checkpoint name and quantization method together from one observed precision candidate. These fields identify a single factor level and cannot be mixed independently; scheduling choices still combine as before, and the resulting configuration gets its own measured launch.

### Completed Qwen README figures

`plot_qwen_performance` displays saved chat-concurrency-32 throughput and TTFT means with their existing confidence intervals. It marks the fixed 500 ms constraint and selected configuration without recomputing statistics or hiding the CI overlap.

`plot_qwen_quality` plots only independent measured quality rows and their saved Wilson intervals. It excludes inherited copies and shows the fixed sample count and paired McNemar result to avoid inflating evidence.

`plot_qwen_regressions` counts the report's existing corrected verdicts by tested candidate. Inconclusive results and the descriptive A/A count remain visible, while the unsupported untested AWQ variant is explicitly excluded.

`plot_progress` now also renders a completed snapshot, and `main` rebuilds the GPT-OSS, Qwen and completion images from committed sources. These display changes do not alter campaign statistics or invoke a live model.

`report.plots` now allocates width for the number of configurations and angles long labels. This prevents the real nine-configuration report from overlapping names while preserving every plotted statistic and replication count.

### M11 release verification

`cli.dispatch` now exposes the package version through argparse's standard version action. It exits before requiring a subcommand, so an installed artifact can identify itself without loading a model.

`test_released_schema_v1_snapshot` compares the active DDL with the released SQL snapshot and its fixed SHA-256. This guards the storage contract against accidental drift when package versions change.


### Post-release figure replication caption

`replication_caption` reads the distinct rep/launch counts from stored aggregates
and groups them by baseline versus candidate. It lists heterogeneous counts rather
than silently claiming every candidate has the same replication.
