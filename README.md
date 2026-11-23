# InferencePilot

InferencePilot is being built to compare tested vLLM serving configurations with
replicated launches, noise-aware statistics, paired quality checks, and a
constraint-based recommendation. **Current stage: M1 configuration and experiment planning.**
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
- [ ] M2–M8 statistics, adapters, runner, quality, detector, and reports.
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
