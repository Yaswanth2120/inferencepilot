# InferencePilot

InferencePilot is being built to compare tested vLLM serving configurations with
replicated launches, noise-aware statistics, paired quality checks, and a
constraint-based recommendation. **Current stage: M4 benchmark adapter and metrics.**
There are no live benchmark results yet.

## Quickstart (no GPU)

Use Python 3.10–3.12. From the repository root:

```sh
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
inferencepilot selftest
inferencepilot doctor
```

`selftest` currently checks CLI wiring only and says the full pipeline is pending
M6. The pytest suite exercises the actual fake HTTP server and subprocess.
`doctor` prints a JSON environment snapshot and exits 3 when vLLM, NVIDIA tools,
or lm-eval are absent. This is expected on a development Mac; offline tests do
not need those tools. It never loads a model or imports vLLM.

## Status

- [x] Editable install verified on macOS, Python 3.12.9.
- [x] Offline tests: streaming text/chat, seeded jitter, applied slowdown,
  prefill/concurrency scaling, failures/hangs, and fake benchmark JSON.
- [x] Fake executable launches over PATH, exposes health/models, prints
  provisional resolved configuration, and cleans up its child after SIGTERM.
- [x] Doctor handles unavailable tools and captures a best-effort snapshot.
- [x] Ruff check and the explicitly limited M0 selftest run locally.
- [x] M0 setup passed all six macOS/Linux and Python 3.10–3.12 CI jobs.
- [x] M1 deterministic OFAT plans, baseline placement, calibration estimate, and dry-run.
- [x] M1 configuration validation and missing-flag checks against fake full help.
- [x] M2 descriptive statistics, seeded bootstrap/permutation tests, Holm, Wilson, McNemar, and MDE.
- [x] M3 owned process groups, readiness, provisional resolved logs, safety checks, and load/factor probes.
- [x] M4 benchmark argv snapshots, detailed-result parser, metric cross-checks, failure classification, and measured-capacity open-loop rates.
- [ ] M5–M8 quality, runner, detector, and reports.
- [ ] M9 live campaign: **not run (needs GPU)**.

No rental GPU is needed for M0–M8. Rent only when M9 prerequisites are ready;
AGENTS.md specifies the owner-driven A100 campaign.

## Offline fake tools

The executable is isolated from the normal PATH. With the virtualenv activated:

```sh
export PATH="$PWD/src/inferencepilot/fakes/fake_bin:$PATH"
vllm serve fake-model --port 8000 --seed 7
# In another activated terminal with the same fake PATH:
vllm bench serve --num-prompts 3 --save-result --save-detailed \
  --result-dir data/raw --result-filename fake.json
```

The fake bench emits deterministic synthetic JSON; it does not send load to the
server and must never be treated as performance evidence. Interface and fixtures
are provisional until checked against owner-provided real output in M9.
Server controls use `INFERENCEPILOT_FAKE_` plus uppercase setting names:
`TOKEN_DELAY`, `PREFILL_PER_TOKEN`, `CONCURRENCY_SLOWDOWN`, `JITTER`,
`INJECT_SLOWDOWN_PCT`, `FAILURE_RATE`, `HANG_RATE`, and `HANG_SECONDS`.
Set `INFERENCEPILOT_FAKE_CRASH=1` to simulate startup failure. Tokenization is
whitespace-based and output tokens are deterministic strings, not model output.

## Prior art and scope

vLLM 0.15.1 already provides [parameter sweeps](https://docs.vllm.ai/en/v0.15.1/benchmarking/sweeps/),
server startup, repeated runs, resume, SLA tuning, and visualization. Those are
not claimed as novel. InferencePilot's intended focus is replicated launch
placement, statistical comparisons with MDE and multiple-test correction,
count-backed detector validation, paired quality checks, and recommendations
with uncertainty. M1 implements planning; the statistical features come later.
See [versioned compatibility notes](docs/VLLM_COMPATIBILITY.md) for sources and
remaining live verification.
No web UI, cloud rental orchestration, multi-GPU serving, or other engines are
planned. Synthetic workloads and fake measurements cannot establish real
latency, quality, quantization compatibility, or speedups. Real results will be
limited to the pinned software, model, GPU, workload, and measured noise floor.

See AGENTS.md for the master specification, DECISIONS.md for choices,
EXPLAINED.md for function explanations, and docs/ for current design/runbook
status. `make campaign` and `make report` fail explicitly until implemented.

## Local environment note

This workspace marked files inside `.venv` as hidden on macOS. Python then
skipped the editable-install `.pth` file. A normally named `venv/` avoids this
local issue; no import-path workaround was added to the package or tests.
Git is now initialized; the snapshot records the current commit when available.

## Recorded M0 verification

Local macOS / Python 3.12.9 run:

```text
python -m pip install -e '.[dev]'  -> Successfully installed inferencepilot-0.0.1
pytest                          -> 17 passed in 1.90s
ruff check .                    -> All checks passed!
inferencepilot selftest         -> M0 CLI wiring OK; full pipeline pending M6
inferencepilot doctor           -> exit 3; missing vLLM/NVIDIA/lm-eval reported
```

The subsequent M0 setup passed [all six CI jobs](https://github.com/Yaswanth2120/inferencepilot/actions/runs/45218908132).
Live paths: not run (needs GPU).


## M1 planning quickstart

With the virtualenv activated:

```sh
mkdir -p data
inferencepilot plan --config configs/experiment_qwen3_8b.yaml --out data/plan.json
inferencepilot run --plan data/plan.json --db data/demo.db --dry-run
```

The example plans 12 launches: three baselines, seven OFAT candidates, one
unresolved combined candidate, and one seeded eager regression. Baselines occupy
indices 0, floor(total/2), and total-1. The same input and seed produce byte-identical
JSON, and each point contains five stored rep seeds. Requested flags remain
requests until the server's resolved configuration is captured.

The illustrative estimate is 5.9067 GPU hours from **synthetic calibration**;
it is not a measured campaign duration. It includes warmup estimates, startup,
teardown, and a 600-second extra reserve. Open-loop runtime is excluded until
baseline capacity is measured; allocate additional budget then. The budget flag
in M1 previews the cap; enforcement and actual execution arrive in M6.

The interface target is pinned to vLLM 0.15.1. `doctor --vllm-bin PATH` checks its
version and all currently used serve flags against full help. Real hardware
compatibility and flag effectiveness are unverified: not run (needs GPU).

## Repository workflow and license

Public repository: https://github.com/Yaswanth2120/inferencepilot. Licensed under
[MIT](LICENSE). `main` requires a PR, six successful offline CI jobs, a branch
up to date with main, and resolved conversations; force pushes and deletion are
blocked. M0 has a historical branch; M1 and every future milestone have named
branches as requested. Future branches are reserved references, not completed
milestones. See [CONTRIBUTING.md](CONTRIBUTING.md) for branch names, conventional
commits, and the squash-merge workflow.

M1 local verification (macOS, Python 3.12.9):

```text
pytest                  -> 63 passed in 3.33s
ruff check .            -> All checks passed!
inferencepilot selftest -> M0 CLI wiring OK; full pipeline pending M6
plan + run --dry-run    -> 12 launches, 8 points each, 5.9067 illustrative GPU hours
```

M1 live paths: not run (needs GPU).


## M2 statistics

`inferencepilot.stats` uses only the Python standard library. Percentiles follow
linear/type-7 interpolation: sort x, set h=(n-1)*p/100, and interpolate between
the observations at floor(h) and ceil(h). SD uses the sample denominator n-1;
CV is a dimensionless SD/abs(mean), undefined at a zero mean.

Bootstrap intervals resample scalar **rep-level** statistics, not individual
requests: 10,000 resamples and a local seed by default. Two-sample permutation
tests use absolute mean difference and enumerate up to 20,000 label assignments;
larger problems use 100,000 seeded assignments with a conservative +1 correction.
Holm adjustment preserves the input test order. Wilson intervals use the score
formula, and McNemar uses the exact two-sided binomial discordance test.

MDE estimates separate between-launch and within-launch variance. With the
three-baseline/one-candidate design, candidate launch noise stays in the standard
error even if many reps are collected within that launch. It is a **normal
planning approximation**, not a guaranteed power claim; M7 validates actual
false-positive rate and power. See DECISIONS.md for the full derivation,
assumptions, edge cases, and worked arithmetic. No GPU rental is needed.

M2 local verification (macOS, Python 3.12.9):

```text
pytest                  -> 130 passed in 3.70s (67 new cases)
ruff check .            -> All checks passed!
inferencepilot selftest -> M0 CLI wiring OK; full pipeline pending M6
```

The no-NumPy import check scans every Python module under src. Detector power
validation is still M7. Live paths: not run (needs GPU).


## M3 server lifecycle and probes

`ServerManager` starts one server in a new process group, captures its output
under `data/logs/<launch_id>.log`, and waits for both health and the expected
model. Before starting it checks the port, a single visible GPU below 2048 MiB
used memory, existing vLLM processes, and the pinned version/flag contract.
Unavailable safety tools cause refusal. It never terminates a process found by
inspection; stop an image's auto-launched server yourself before the campaign.

Shutdown signals only the group this manager started, waits up to 60 seconds,
and escalates to SIGKILL if necessary. It then waits up to 120 seconds for GPU
memory below the idle threshold. A cleanup failure is recorded and blocks a
subsequent start. Read-only process inspection distinguishes exited/zombie
groups from active processes; permission failures on a live group remain errors.

GPU-machine commands for later owner execution:

```sh
inferencepilot probe --model Qwen/Qwen3-8B --variant bf16
inferencepilot probe --model Qwen/Qwen3-8B --variant fp8_online
inferencepilot probe --model Qwen/Qwen3-8B-AWQ --variant awq
inferencepilot probe --model Qwen/Qwen3-8B-FP8 --variant fp8_ckpt
inferencepilot probe --model Qwen/Qwen3-8B --variant chunked_prefill
inferencepilot probe --model Qwen/Qwen3-8B --variant kv_cache_fp8
```

The chunked-prefill probe launches both directions and compares resolved values
against requests. Missing or ignored resolved settings do not count as honored.
Probe JSON defaults to `data/probes/` and contains requested settings, per-launch
status, timing, log paths, parsed lines, cleanup state, and a failure log tail.
Use `--out` to select a new file; existing probe outputs and launch logs are not
overwritten. Exit 3 means a failed or unhonored probe/environment; exit 2 means
invalid configuration or output-file errors. Failed loads are recorded as
`unsupported_on_hardware` per launch, without proving the precise root cause.

All startup parsing is **provisional** and omits fields not observed in logs;
requested flags are never substituted as resolved values. Fake KV capacity,
attention backend, and graph mode are synthetic fixtures, not GPU measurements.
Real logs and quantized-load compatibility still require owner output in M9.
Do not rent a GPU yet: M4–M8 remain offline prerequisites.

M3 local verification (macOS, Python 3.12.9):

```text
pytest                  -> 177 passed in 25.61s (47 new cases)
ruff check .            -> All checks passed!
inferencepilot selftest -> M0 CLI wiring OK; full pipeline pending M6
```

Verified offline: startup/readiness, provisional parsing, startup crash/OOM
classification, bounded failure logs, hangs/unhealthy/wrong-model refusal,
owned child cleanup, TERM/KILL escalation, GPU-busy and cleanup safety gates,
foreign-process survival, interruptions, and persistent load/factor probe evidence.
Live GPU and real vLLM paths: not run (needs GPU).


## M4 benchmark adapter and metrics

`loadgen.build_command` wraps the pinned `vllm bench serve` interface. It always
requests streaming raw completions, fixed lengths, ignored EOS, temperature 0,
seeded input, ten warmups by default, detailed saved JSON, and TTFT/TPOT/ITL/E2E
p50/p95/p99 summaries. Random lengths have range ratio zero. The prefix workload
uses one shared prefix of 2048 tokens, a 256-token suffix, and 128 output tokens.
Eight closed-loop points and three sample open-loop rates have exact argv snapshots.

Closed-loop uses an infinite arrival rate with a concurrency cap; open-loop uses
a finite rate with burstiness 1 and no client concurrency cap. The adapter builds
arguments and parses artifacts; M6 will own invocation, scheduling, storage, and
wall-clock budget enforcement. It does not implement a load generator.

The pinned JSON has no per-request E2E array. `metrics` reconstructs E2E from
TTFT plus streaming gaps and verifies p99 against the tool's reported value.
A small first-token clock-reading skew is possible; this is provisional until
real fixtures are collected. Streaming gaps may bundle output tokens, so pooled
ITL and per-request token-average TPOT are explicitly distinct views.

The parser requires aligned numeric detailed arrays and consistent outcome counts.
Metrics fail with `AdapterBrokenError` if mean TTFT, p99 E2E, output throughput,
or request throughput differs by **more than 1%**, or token totals disagree.
Transport errors and output-length violations are counted separately; more
than 1% failures makes a rep partial and excluded from comparisons. Exactly
1% remains eligible with a visible note. With no valid full-length requests,
the rep is failed. Empty distributions have n=0 and null statistics.

Latency distributions and SLO goodput exclude non-fixed-length responses;
physical token/request throughput follows the tool and includes all transport
successes. A one-token response has no TPOT distribution observation; for
SLO goodput only, its TPOT is zero as defined by the pinned tool. Every derived
distribution and rate carries its request/gap count and units.

For later scheduling, `baseline_chat_capacity` takes comparable baseline-chat
closed-loop reps grouped by concurrency, uses each point's mean rep throughput,
and chooses the largest tested point mean. Its result includes the selected
concurrency, rep count, and excluded-rep count. `open_loop_loads` derives 50%,
80%, and 95% rates from that measured estimate; it never invents a capacity
from configuration settings. The caller must supply baseline/chat/closed data.

All benchmark fixtures are synthetic/provisional. Real `vllm bench serve`
compatibility and GPU measurements: not run (needs GPU).

M4 local verification (macOS, Python 3.12.9):

```text
pytest                  -> 237 passed in 33.06s (60 new cases)
ruff check .            -> All checks passed!
inferencepilot selftest -> M0 CLI wiring OK; full pipeline pending M6
```

Verified: 11 exact argv snapshots, strict result parsing, hand-worked TTFT/E2E/
pooled-ITL/TPOT/throughput/goodput, greater-than-1% mismatch detection, exact
failure thresholds, truncation/zero-output accounting, measured-capacity rates,
and built-command execution against the fake benchmark in both load modes.
Real GPU and vLLM paths: not run (needs GPU).
