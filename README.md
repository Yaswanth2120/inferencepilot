# InferencePilot

InferencePilot is being built to compare tested vLLM serving configurations with
replicated launches, noise-aware statistics, paired quality checks, and a
constraint-based recommendation. **Current stage: M0 offline foundation.**
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
- [ ] Linux and the full Python 3.10–3.12 matrix verified (CI configured only).
- [ ] M1–M8 planner, statistics, adapters, runner, quality, detector, and reports.
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

vLLM already supplies benchmark tooling; GuideLLM and similar tools generate
load. InferencePilot's planned contribution is lifecycle orchestration,
replicated experiments, noise-aware comparisons with MDE, detector validation,
paired quality evaluation, and recommendations among tested configurations.
These features are not implemented in M0. Before M1, select a pinned vLLM
version and inspect its sweep capabilities to refine this comparison.

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
The workspace currently has no Git repository, so the snapshot reports the Git
SHA as unavailable until the owner initializes one.

## Recorded M0 verification

Local macOS / Python 3.12.9 run:

```text
python -m pip install -e '.[dev]'  -> Successfully installed inferencepilot-0.0.1
pytest                          -> 17 passed in 1.90s
ruff check .                    -> All checks passed!
inferencepilot selftest         -> M0 CLI wiring OK; full pipeline pending M6
inferencepilot doctor           -> exit 3; missing vLLM/NVIDIA/lm-eval reported
```

Linux CI has not run. Live paths: not run (needs GPU).
