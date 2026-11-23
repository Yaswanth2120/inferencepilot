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
