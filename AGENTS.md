# InferencePilot: Master Specification

Single source of truth. Save as `AGENTS.md` in the root of the `inferencepilot` repo. Read it fully at the start of every session. If code and this document disagree, stop and report; do not silently pick one.

---

## 0. How to work (session protocol)

1. The owner starts each session with: `Work on Milestone N.` Do only that milestone.
2. First reply: restate the milestone's acceptance criteria in your own words and list the files you will touch. Then implement.
3. Run `pytest` and `ruff check .` before declaring anything done. Never leave the suite red. Never delete or weaken a test to make it pass; if intended behavior changed, say so explicitly.
4. **You cannot run a GPU or vLLM.** Any code that needs them is covered by offline tests against the fake server (section 8) and by recorded fixtures. Tests that need a real GPU/vLLM carry `@pytest.mark.live` and are skipped by default. In every report write "not run (needs GPU)" for those. Never claim a live path works unless the owner pasted real output proving it.
5. At the end of each milestone produce: passing test output; the README status checklist updated (tick only what was run and verified); `DECISIONS.md` entries for every ambiguous choice; `EXPLAINED.md` entries (2-3 plain sentences per new function: what it does and why it is written that way); a final report listing files changed, tests added, anything unfinished, and anything in existing code you believe is wrong.
6. Flag problems in existing code; do not fix them outside the milestone's scope.
7. No dependencies beyond section 14. The owner must be able to explain every line in an interview: small functions, plain names, no clever abstractions, comments only for non-obvious "why". Do not claim anything works that you have not run.
8. **vLLM flag names change between versions.** Never trust flag names written in this document as final. All vLLM flag names live in one file, `src/inferencepilot/vllm_flags.py`. The `doctor` command checks every flag the code uses against the `--help` output of the pinned vLLM and fails fast on a mismatch.

---

## 1. Product definition

**InferencePilot automatically benchmarks LLM serving configurations on vLLM and recommends the best tested configuration, with statistically defensible comparisons of latency, throughput, concurrency behavior, and model quality.**

It owns orchestration, statistics, regression detection, quality checks, and reporting. It does **not** write its own load generator (it wraps `vllm bench serve`), and it does not modify vLLM.

### Why this is not a clone of existing tools (put this in the README)
`vllm bench serve` measures one configuration once. GuideLLM and similar tools generate load. InferencePilot's contribution is the layer above: server lifecycle management per configuration, designed experiments with replicated launches, noise-aware regression detection with a stated minimum detectable effect, paired quality evaluation, a constraint-based recommender, and a validated detector (false-positive rate and power measured). Before M1, check whether the pinned vLLM ships `vllm bench sweep` or similar; if it does, document precisely how InferencePilot differs and do not claim novelty it lacks.

### Non-goals (do not build)
- Multi-GPU, tensor parallelism, multi-node, autoscaling, Kubernetes.
- Engines other than vLLM (an adapter interface may exist; only vLLM is implemented).
- Training, fine-tuning, quantizing models ourselves (use published checkpoints and vLLM's online quantization).
- Bayesian/adaptive optimization (stretch only, after v0.1.0).
- Web UI, auth, multi-tenant anything, cloud orchestration of the GPU rental itself.
- Cost modeling beyond GPU-hours.

---

## 2. End-state deliverables (definition of "finished", v0.1.0)

1. Installable package `inferencepilot` with CLI `inferencepilot`.
2. `ServerManager` that launches, health-checks, captures logs from, and tears down `vllm serve` per configuration, and records the *resolved* configuration the server actually used.
3. Adapter around `vllm bench serve` producing raw per-request metrics; own statistics computed from raw data and cross-checked against the tool's reported numbers.
4. Experiment planner (one-factor-at-a-time around a baseline plus a combined candidate), resumable scheduler with randomized order, warmups, and a wall-clock GPU budget cap.
5. Statistics engine (pure Python): percentiles, bootstrap CIs, exact permutation tests, Holm correction, minimum detectable effect.
6. Regression detector validated by an A/A false-positive test, a power curve with injected synthetic slowdowns, and a real seeded regression.
7. Quality evaluation: lm-evaluation-harness against the running server (fixed dataset), paired McNemar comparison, and a greedy-output agreement check.
8. Constraint-based recommender and a generated report (Markdown + JSON + plots).
9. Fake vLLM server and recorded fixtures so everything except the live campaign is tested offline.
10. A completed live campaign on Qwen3-8B (BF16 baseline, quantized variants), results committed under `reports/`. Optional: GPT-OSS-120B serving validation.
11. CI workflow (offline only), `docs/DESIGN.md`, README with quickstart, results table, limitations. Tag `v0.1.0`.

---

## 3. Architecture

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │ CLI (argparse; wiring only)                                            │
 └───────┬───────────────────────────────────────────────────────────────┘
         │
 ┌───────▼────────┐   plan    ┌──────────────────┐
 │ Planner        │──────────▶│ Scheduler/Runner │  resumable, budget-capped,
 │ (OFAT design,  │           │ (randomized      │  warmups, checkpoints
 │  cost estimate)│           │  order)          │
 └────────────────┘           └───┬──────────┬───┘
                                  │          │
                 ┌────────────────▼──┐   ┌───▼─────────────────────┐
                 │ ServerManager     │   │ Env snapshot + GPU       │
                 │ vllm serve (proc) │   │ telemetry (nvidia-smi)   │
                 │ health, logs,     │   └──────────────────────────┘
                 │ resolved config   │
                 └───────┬───────────┘
                         │ HTTP (OpenAI-compatible)
        ┌────────────────┼──────────────────────┐
        ▼                ▼                      ▼
 ┌─────────────┐  ┌──────────────┐   ┌────────────────────┐
 │ LoadGen     │  │ Quality      │   │ Agreement check    │
 │ adapter     │  │ (lm-eval     │   │ (greedy outputs    │
 │ (vllm bench │  │  gsm8k)      │   │  vs reference      │
 │  serve)     │  └──────┬───────┘   │  config)           │
 └──────┬──────┘         │           └─────────┬──────────┘
        │ raw per-request JSON                 │
 ┌──────▼──────────────────────────────────────▼─────────┐
 │ Store: SQLite (summaries, configs, launches, results)  │
 │        + raw JSON files under data/raw/                │
 └──────┬──────────────────────────────────────┬─────────┘
        │                                      │
 ┌──────▼────────┐  ┌───────────────┐  ┌───────▼────────┐
 │ Stats engine  │─▶│ Regression    │─▶│ Recommender    │──▶ Report
 │ (pure Python) │  │ detector      │  │ (constraints,  │   (md/json/png)
 └───────────────┘  └───────────────┘  │  Pareto)       │
                                       └────────────────┘
```

### Module responsibilities
| Module | Owns | Must not |
|---|---|---|
| `vllm_flags.py` | every vLLM flag name and the ConfigSpec-to-argv mapping | contain logic |
| `config.py` | Pydantic ConfigSpec, WorkloadSpec, Experiment plan | do I/O |
| `planner.py` | experiment design, cost/time estimate | start processes |
| `server.py` | subprocess lifecycle, health, log capture, resolved-config parsing | run benchmarks |
| `loadgen.py` | `vllm bench serve` command builder and raw-result parser | compute statistics |
| `stats.py` | percentiles, bootstrap, permutation, Holm, MDE (pure Python) | do I/O |
| `metrics.py` | derive TTFT/ITL/E2E/throughput from raw per-request arrays | start processes |
| `quality.py` | lm-eval wrapper, per-sample parsing, McNemar, Wilson, agreement check | start servers |
| `regress.py` | baseline-vs-candidate comparison and verdicts | do I/O besides store reads via arguments |
| `recommend.py` | constraint filter, Pareto set, ranking, explanations | recompute statistics |
| `runner.py` | orchestration, resume, budget cap, ordering | compute statistics |
| `store.py` | all SQL and raw-file paths | contain business logic |
| `env.py` | environment snapshot, `nvidia-smi` telemetry | |
| `report.py` | render Markdown/JSON/plots from the store | recompute numbers differently from `stats.py` |
| `fakes/fake_vllm.py` | fake OpenAI-compatible server with controllable latency, plus fake `bench` output | be imported by library code |
| `cli.py` | argparse wiring only | contain logic |

---

## 4. Glossary
- **ConfigSpec**: the full set of server arguments for one configuration (model, quantization, flags).
- **Launch**: one start-to-stop lifetime of a `vllm serve` process under a ConfigSpec. Server restarts are a source of variance; launches are the unit of replication for between-run noise.
- **Workload**: dataset shape and token lengths (e.g., chat-256/256).
- **Point**: a workload at one load level (a concurrency cap, or an arrival rate).
- **Rep**: one execution of a point (one `vllm bench serve` invocation).
- **Baseline / candidate**: reference configuration and the configuration compared against it.
- **MDE**: minimum detectable effect, the smallest percent change the experiment could reliably detect given observed noise.

---

## 5. Experiment design

### 5.1 Factors (verify flag names via `doctor`; centralize in `vllm_flags.py`)
| Factor | Levels | Notes |
|---|---|---|
| Weights/quantization | `bf16` (`Qwen/Qwen3-8B`); `fp8_online` (BF16 weights, vLLM online FP8 quantization); `awq` (`Qwen/Qwen3-8B-AWQ`); `fp8_ckpt` (`Qwen/Qwen3-8B-FP8`) | A100 has no native FP8 compute. vLLM documents FP8 on Ampere as weight-only (W8A16) via Marlin. The Qwen docs describe the official FP8 checkpoint as block-wise FP8 supported for compute capability above 8.9, so it may not load on A100. `doctor`/M3 run a *load probe* per variant; a variant that fails to load is recorded as `unsupported_on_hardware` with the log tail, not silently dropped. Do not assume any quantized variant is faster on A100: measure. |
| Prefix caching | on / off | Always pass the explicit flag in both directions; the default is version-dependent. |
| `max_num_batched_tokens` | 2048, 8192, 16384 | This is the effective chunk budget. |
| `max_num_seqs` | 64, 256 | Ceiling on concurrent sequences, not the realized batch. |
| Chunked prefill | probe only | Reports conflict on whether the V1 engine always enables chunked prefill and whether a flag can disable it, and behavior varies by version. Run a *factor probe*: launch with the flag both ways, parse the resolved config from the startup log. If the setting is not honored, drop the factor and say so in the report. Never label a configuration by its CLI flag alone; label by the resolved value. |
| KV cache dtype | auto / fp8 | Optional, probe-gated; skip if the server refuses. |
| `--enforce-eager` | off (baseline) / on | Candidate for the seeded real regression (disables CUDA graph capture; expected to slow decode, magnitude to be measured, not assumed). |
| Fixed | `--dtype bfloat16`, `--gpu-memory-utilization 0.90`, `--max-model-len 8192` (Qwen3 phase), port, seed | Record all in the config. |

### 5.2 Design
- **Baseline**: bf16, prefix caching on, `max_num_batched_tokens=8192`, `max_num_seqs=256`, no eager.
- **One-factor-at-a-time (OFAT)** candidates: each level of each factor against the baseline, others fixed. Roughly 7-9 configurations. Plus one **combined** candidate assembled from the best individual levels, validated as its own run (interactions are not assumed away).
- **Baseline replication:** run the baseline as **3 independent launches** (first, middle, last of the schedule, to expose drift). Their between-launch spread sets the noise floor and the MDE.
- Candidates: 1 launch each, 5 reps per point.
- Configuration order is randomized with a fixed seed except the baseline placement above. The seed is stored.
- Full factorial is out of scope (cost). State in the report that interactions are only checked via the combined candidate.

### 5.3 Workloads (all with fixed output length, `ignore_eos`, fixed seeds per rep; lengths in tokens)
| Name | Dataset | Input/Output | Closed-loop concurrency | Prompts per rep |
|---|---|---|---|---|
| `chat` | random | 256 / 256 | 1, 8, 32, 64 | 200 |
| `rag` | random | 4096 / 256 | 4, 16 | 100 |
| `prefix` | prefix-repetition | shared prefix 2048 + suffix 256 / 128 | 16, 64 | 200 |

- Warmups: discard the first N requests via the tool's warmup option (default 10) before measuring.
- **Open-loop stage (after capacity is known):** for `chat`, pick arrival rates at 50%, 80%, and 95% of the baseline's measured closed-loop max request throughput. Latency under load is meaningful only open-loop; closed-loop numbers measure capacity.
- Reps per point: 5 (baseline launches: 5 each, so 15 pooled).
- Estimated time per rep is computed by the planner from a short calibration; the planner prints total GPU hours before anything runs.

### 5.4 Budget guard
`--max-gpu-hours H` (wall-clock). The runner checks before each launch and each point, stops cleanly when exceeded, marks the experiment `aborted` with a reason, and keeps everything collected. `inferencepilot run --dry-run` prints the schedule and estimated hours. Default cap for the Qwen3 campaign: 14.

---

## 6. Metrics and statistics

### 6.1 Metric definitions (compute from raw per-request arrays, `--save-detailed` output)
- **TTFT**: time to first token per request.
- **ITL**: inter-token latencies; report two views and label them: *pooled* (all gaps from all requests) and *per-request mean (TPOT)*.
- **E2E latency** per request.
- **Output throughput** (tokens/s) = total output tokens / benchmark duration; **request throughput** (req/s).
- **Goodput**: requests per second meeting an SLO triple (TTFT, TPOT, E2E thresholds) from the constraints file.
- Percentiles p50, p95, p99 with linear interpolation (document the exact formula; must equal NumPy's default method on the same data, tested against hand-computed values).
- Failed or truncated requests are counted and reported; a rep with more than 1% failures is `partial` and excluded from comparisons with a visible note.
- **Cross-check:** for every rep, recompute the tool's own reported summary numbers (mean TTFT, p99 E2E, throughput) from raw data; mismatch beyond 1% marks the adapter broken (this catches parser bugs).

### 6.2 Statistics (`stats.py`, no numpy/scipy; every function unit-tested against hand-computed values written in the test comments)
- Percentile (linear interpolation), mean, median, standard deviation, coefficient of variation.
- Percentile bootstrap CI: 10,000 resamples, fixed seed. The **rep is the resampling unit** (requests within a rep are correlated through shared server state; do not treat pooled requests as independent).
- Exact two-sample permutation test on rep-level statistics when the number of label permutations is ≤ 20,000, otherwise Monte-Carlo with 100,000 permutations and a fixed seed.
- Holm-Bonferroni correction across all (workload, point, metric) tests in one candidate-vs-baseline comparison.
- Wilson interval for proportions; exact McNemar test for paired binary outcomes.
- **MDE**: from the baseline's between-launch and within-launch variability, compute the smallest percent change detectable at α = 0.05 with 80% power (document the formula used; derive it in `DECISIONS.md`). Report MDE next to every comparison.

---

## 7. Regression detector

For each `(workload, point, metric)`:
- Inputs: baseline rep-level values (pooled across the 3 launches) and candidate rep-level values.
- Metric directions: latencies lower-is-better; throughput higher-is-better.
- Outputs: effect (percent change), bootstrap CI, permutation p, Holm-adjusted p, MDE, verdict.
- **Verdict rules:** `regression` if adjusted p < 0.05 and the worse-direction effect ≥ `min_effect_pct` (default 5%); `improvement` symmetric; `no_change` if the CI lies inside ±`min_effect_pct`; otherwise `inconclusive`. Also `inconclusive` whenever MDE > `min_effect_pct` (the experiment could not have seen the effect) or reps < 5.
- Summary-level verdict per candidate: the worst per-point verdict, plus counts.

### Validation of the detector itself (required; this is the project's credibility)
1. **A/A test:** split the baseline's 3 launches (e.g., launch 1 vs launches 2-3 in every combination), run the detector, and report the false-positive rate over all tests. Expected near or below α after correction; report the actual number with the count of tests.
2. **Power curve (offline):** the fake server injects a controlled added latency of +2%, +5%, +10%, +20%. Report detection rate vs injected effect over repeated simulated experiments (fixed seeds).
3. **Real seeded regression (live):** a candidate expected to be worse (default `--enforce-eager`; alternatively very low `max_num_seqs`). It must be flagged on at least one primary metric. If not, report that honestly and investigate noise; do not tune thresholds after seeing the result without recording it in `DECISIONS.md`.

---

## 8. Fake server and fixtures (the offline test backbone)

- `fakes/fake_vllm.py`: FastAPI app exposing `GET /health`, `GET /v1/models`, `POST /v1/completions` and `POST /v1/chat/completions`, with streaming. Latency model is controllable: per-token delay, prefill cost proportional to prompt tokens, a concurrency-dependent slowdown, jitter from a seeded RNG, an `inject_slowdown_pct`, and failure injection (500s, hangs).
- A fake `vllm` executable (a script on `PATH` in tests) that accepts the same argv, prints startup log lines in the same shape as real vLLM (including resolved-config lines), serves the fake app, and exits on SIGTERM. This lets `ServerManager` be tested end to end as a real subprocess.
- A fake `vllm bench serve` producing JSON in the real schema, including `--save-detailed` arrays.
- **Fixtures from reality:** after the first live session the owner commits real startup logs and real `bench` JSON under `tests/fixtures/real/`. Parsers must be tested against those. Until then parsers are tested against fixtures written from the vLLM docs and marked `provisional`; M9 replaces them.

---

## 9. Quality evaluation

### 9.1 lm-evaluation-harness (primary)
- Run against the *running server* (not an in-process model; the GPU is occupied by the server): `lm_eval --model local-completions --model_args model=<served name>,base_url=http://127.0.0.1:<port>/v1/completions,tokenized_requests=False --tasks gsm8k --num_fewshot 5 --log_samples --output_path <dir>` (verify arguments against the pinned lm-eval).
- Greedy decoding, fixed few-shot, full test split (1,319 problems) unless the time budget demands a fixed subset; the subset definition (first N in dataset order) is stored with results.
- This uses raw completions, so no chat template or thinking mode is involved; state that caveat. Comparisons are relative between configurations, not absolute Qwen3 scores.
- Parse per-sample correctness from `--log_samples` output. Report exact-match (both flexible and strict filters), Wilson 95% CI, and **paired exact McNemar test vs the BF16 baseline** on per-sample correctness.
- Quality is evaluated once per launch that changes weights/precision. Scheduling-only changes (e.g., `max_num_batched_tokens`) are not expected to change outputs; evaluate quality once on the baseline and once on the combined candidate to verify.

### 9.2 Greedy agreement check (secondary, independent of lm-eval)
- 200 fixed prompts, temperature 0, fixed max tokens, requests sent directly. Compare each configuration's output tokens to the BF16 baseline's: exact-match rate and mean position of first divergence. Quantization changes are expected to cause divergences; this quantifies how many. Non-quantized scheduling changes should show near-100% agreement; report any deviation as a finding (batch-composition effects can cause small numerical differences, so do not call a deviation a bug without evidence).

---

## 10. Recommender

- Input: a constraints YAML (`constraints.yaml`): SLO points (e.g., `chat@32: p95_ttft_ms <= 500, p95_e2e_ms <= 15000`), minimum quality (e.g., gsm8k flexible-extract drop ≤ 1.0 percentage point vs BF16 and McNemar not significant at 0.05), objective (default: maximize output tokens/s at a stated SLO point).
- Filter configurations by constraints; rank survivors by the objective; produce the Pareto set over (throughput, p95 E2E latency, quality).
- Every rejected configuration gets the specific constraint it failed and by how much.
- Output language: "best **tested** configuration under these constraints". Never extrapolate to untested combinations. Include the MDE and any `inconclusive` comparisons that touch the decision.

---

## 11. Data model (SQLite, stdlib `sqlite3`, WAL mode, foreign keys ON)

```sql
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS env_snapshots (
    id         TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    data       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    created_at        REAL NOT NULL,
    plan              TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('planned','running','completed','aborted')),
    abort_reason      TEXT,
    env_id            TEXT REFERENCES env_snapshots(id),
    budget_gpu_hours  REAL,
    seed              INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS configs (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('baseline','candidate','seeded_regression','combined')),
    spec          TEXT NOT NULL,
    spec_hash     TEXT NOT NULL,
    UNIQUE (experiment_id, label)
);

CREATE TABLE IF NOT EXISTS launches (
    id               TEXT PRIMARY KEY,
    config_id        TEXT NOT NULL REFERENCES configs(id) ON DELETE CASCADE,
    ordinal          INTEGER NOT NULL,
    started_at       REAL NOT NULL,
    ready_at         REAL,
    stopped_at       REAL,
    status           TEXT NOT NULL CHECK (status IN ('ok','server_failed','unsupported_on_hardware','aborted')),
    cmd              TEXT NOT NULL,
    resolved_args    TEXT NOT NULL DEFAULT '{}',
    startup_seconds  REAL,
    log_path         TEXT,
    error            TEXT,
    UNIQUE (config_id, ordinal)
);

CREATE TABLE IF NOT EXISTS points (
    id            TEXT PRIMARY KEY,
    launch_id     TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,
    workload      TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('closed','open')),
    concurrency   INTEGER,
    request_rate  REAL,
    num_prompts   INTEGER NOT NULL,
    params        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS reps (
    id            TEXT PRIMARY KEY,
    point_id      TEXT NOT NULL REFERENCES points(id) ON DELETE CASCADE,
    rep           INTEGER NOT NULL,
    seed          INTEGER NOT NULL,
    started_at    REAL NOT NULL,
    duration_s    REAL,
    status        TEXT NOT NULL CHECK (status IN ('ok','failed','partial')),
    completed     INTEGER,
    failed        INTEGER,
    raw_path      TEXT,
    summary       TEXT NOT NULL DEFAULT '{}',
    tool_summary  TEXT NOT NULL DEFAULT '{}',
    gpu_before    TEXT,
    gpu_after     TEXT,
    UNIQUE (point_id, rep)
);
CREATE INDEX IF NOT EXISTS idx_reps_point ON reps (point_id);

CREATE TABLE IF NOT EXISTS quality_results (
    id           TEXT PRIMARY KEY,
    launch_id    TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,
    task         TEXT NOT NULL,
    n            INTEGER NOT NULL,
    metrics      TEXT NOT NULL,
    samples_path TEXT,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agreement_results (
    id                    TEXT PRIMARY KEY,
    launch_id             TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,
    reference_launch_id   TEXT NOT NULL REFERENCES launches(id),
    n                     INTEGER NOT NULL,
    exact_match_rate      REAL NOT NULL,
    mean_first_divergence REAL,
    samples_path          TEXT
);

CREATE TABLE IF NOT EXISTS regression_results (
    id                  TEXT PRIMARY KEY,
    experiment_id       TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    baseline_config_id  TEXT NOT NULL REFERENCES configs(id),
    candidate_config_id TEXT NOT NULL REFERENCES configs(id),
    workload            TEXT NOT NULL,
    point_key           TEXT NOT NULL,
    metric              TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('lower_better','higher_better')),
    effect_pct          REAL,
    ci_low              REAL,
    ci_high             REAL,
    p_value             REAL,
    p_adjusted          REAL,
    mde_pct             REAL,
    n_baseline          INTEGER NOT NULL,
    n_candidate         INTEGER NOT NULL,
    verdict             TEXT NOT NULL CHECK (verdict IN ('regression','improvement','no_change','inconclusive'))
);
CREATE INDEX IF NOT EXISTS idx_regress_cand ON regression_results (candidate_config_id, verdict);

CREATE TABLE IF NOT EXISTS recommendations (
    id               TEXT PRIMARY KEY,
    experiment_id    TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    constraints      TEXT NOT NULL,
    ranking          TEXT NOT NULL,
    chosen_config_id TEXT REFERENCES configs(id),
    created_at       REAL NOT NULL
);
```

Raw per-request arrays live in `data/raw/<rep_id>.json` (gitignored except small committed fixtures); only paths and summaries are in SQLite. Never store API keys or tokens.

---

## 12. ServerManager specification

- Builds argv from `ConfigSpec` via `vllm_flags.py`. Launches `vllm serve` as a subprocess in its own process group; stdout/stderr go to `data/logs/<launch_id>.log`.
- **Pre-launch safety checks (refuse to start if any fails):** the port is free; GPU memory used is below 2 GB (`nvidia-smi --query-gpu=memory.used`); no other `vllm` process is running. The Vast.ai `vastai/vllm` template auto-launches its own `vllm serve` from `VLLM_MODEL`/`VLLM_ARGS`; if that server is occupying the GPU, `ServerManager` must fail with a message telling the owner to stop it or choose a non-auto-launching image (see runbook). Never kill a process you did not start.
- Readiness: poll `GET /health` and `GET /v1/models` until success or timeout (default 900 s; startup includes weight load and CUDA graph capture). Record `startup_seconds`.
- **Resolved config:** parse the startup log into a dict (tolerant regexes; keep the raw matched lines). Examples of what to capture: effective max sequence length, prefix caching state, chunked prefill state and chunk budget, quantization method, KV cache size and the "maximum concurrency for N tokens" line if present, attention backend, CUDA graph mode. Parsers are tested against real logs from M9 onward; before then they are `provisional`.
- Failure handling: OOM at startup, port conflict, crash, or timeout produces `launch.status='server_failed'` (or `unsupported_on_hardware` for a load probe), stores the last 200 log lines in `error`, tears down, and the runner continues with the next configuration.
- Teardown: SIGTERM to the process group, wait up to 60 s, then SIGKILL; then poll until GPU memory is released (timeout 120 s) before any next launch. Leaked engine/worker processes are the usual cause of subsequent OOMs; test teardown with the fake `vllm` spawning a child process.
- Environment snapshot per experiment: vLLM version, torch/CUDA/driver versions, GPU name and compute capability, lm-eval version, git SHA, `pip freeze` hash, CPU model, host RAM, `VAST_CONTAINERLABEL`/instance id if present. GPU telemetry (SM clock, memory clock, power, temperature, utilization) sampled before and after every rep via `nvidia-smi --query-gpu=...`.

---

## 13. CLI (argparse; logic lives elsewhere)

```
inferencepilot doctor    [--vllm-bin PATH]                     # env check, flag verification, nvidia-smi, lm-eval presence
inferencepilot probe     --model M --variant NAME              # load probe for quantized variants / chunked-prefill factor
inferencepilot plan      --config experiment.yaml --out plan.json   # designs experiment, prints estimated GPU hours
inferencepilot run       --plan plan.json --db DB [--max-gpu-hours H] [--dry-run]
inferencepilot resume    --db DB --experiment ID
inferencepilot status    --db DB --experiment ID
inferencepilot analyze   --db DB --experiment ID                # metrics + cross-checks
inferencepilot regress   --db DB --experiment ID --baseline LABEL [--min-effect-pct 5]
inferencepilot validate  --db DB --experiment ID               # A/A false-positive test
inferencepilot power     --out reports/power.json              # offline power curve via fake server
inferencepilot recommend --db DB --experiment ID --constraints constraints.yaml
inferencepilot report    --db DB --experiment ID --out reports/
inferencepilot selftest                                         # whole pipeline against the fake server, offline
```
Exit codes: 0 ok; 1 regression verdict found (for `regress` in CI use); 2 usage/config error; 3 environment check failed.

---

## 14. Repo layout, dependencies, tooling

```
inferencepilot/
  AGENTS.md README.md DECISIONS.md EXPLAINED.md Makefile pyproject.toml
  docs/{DESIGN.md,RUNBOOK_GPU.md}
  src/inferencepilot/
    __init__.py vllm_flags.py config.py planner.py server.py loadgen.py
    stats.py metrics.py quality.py regress.py recommend.py runner.py
    store.py env.py report.py cli.py
    fakes/{__init__.py,fake_vllm.py,fake_bin/vllm}
  configs/{experiment_qwen3_8b.yaml,constraints.yaml,workloads.yaml}
  tests/{unit,integration}/...  tests/fixtures/{provisional,real}/
  reports/  data/ (gitignored)
  scripts/{run_campaign.sh,sync_results.sh}
  .github/workflows/ci.yml
```

Approved dependencies (core): `pydantic`, `pyyaml`, `httpx`. Dev/test: `pytest`, `ruff`, `fastapi`, `uvicorn` (fake server only). Extras: `[report]` `matplotlib`; `[live]` `lm-eval[api]` (installed on the GPU box only). **vLLM is never imported** by the library; it is only invoked as a subprocess. No numpy/pandas/scipy in library code (statistics are pure Python and tested). No ORMs. Anything else needs approval.

Makefile: `test`, `lint`, `selftest`, `campaign` (live), `report`.
CI: Python 3.10-3.12 matrix; `ruff check`; `pytest` (offline); `inferencepilot selftest`. CI never touches a GPU.

---

## 15. Milestones (one per Codex session; owner focused hours at 3-4 h/day)

"Tests" means offline pytest unless marked `live`.

### M0: Skeleton, environment check, fakes (~5 h)
Spec: sections 8, 12 (env snapshot), 13 (`doctor`, `selftest` stub), layout, pyproject, CI, fake server and fake `vllm`/`bench` executables.
Acceptance: `pip install -e '.[dev]'` and `pytest` pass on macOS and Linux; fake server serves streaming completions with seeded jitter and controllable slowdown (tested); `doctor` works offline and reports "vllm not found" gracefully; the fake `vllm` binary starts, logs resolved-config-shaped lines, serves, and exits on SIGTERM including its child process.

### M1: Config model, planner, cost estimate (~5 h)
Spec: sections 5.1-5.4, `config.py`, `planner.py`, `vllm_flags.py` mapping with the `doctor` flag check.
Acceptance: planner emits the OFAT + combined + 3-launch-baseline plan as JSON deterministically for a seed (same seed, same file hash); randomization respects the baseline placement rule; `--dry-run` prints schedule and estimated GPU hours from a calibration table; invalid factor combinations rejected with clear errors; flag check detects an intentionally missing flag using the fake `--help`.

### M2: Statistics engine (~6 h)
Spec: section 6.2 completely.
Acceptance: every function has tests with hand-computed expected values shown in comments (percentile vs NumPy-default definition on at least 5 fixed arrays, bootstrap CI reproducibility with fixed seed, exact permutation p-value on a tiny case enumerated by hand, Holm on a worked example, McNemar exact on a 2x2 worked example, Wilson on known values, MDE formula derived in `DECISIONS.md` and tested); no numpy imports anywhere in `src/`.

### M3: ServerManager (~6 h)
Spec: section 12.
Acceptance: against the fake `vllm`: start, readiness, resolved-config parsing (provisional fixtures), startup failure paths (port busy, crash on start, timeout), teardown kills the child tree, pre-launch GPU-busy check (fake `nvidia-smi` on PATH) refuses to start; load-probe logic classifies failure as `unsupported_on_hardware`; never signals a process it did not start (tested).

### M4: Load generator adapter and metrics (~6 h)
Spec: sections 5.3, 6.1, `loadgen.py`, `metrics.py`.
Acceptance: command builder produces the exact argv for each workload/point (snapshot tests); parser handles the tool's result JSON including detailed arrays (provisional fixture; flagged for replacement in M9); metrics recomputed from raw arrays match the tool-reported summary within 1% on the fixture; mismatch triggers an adapter-broken error; failed/partial rep classification tested; open-loop arrival rate derived from a measured capacity.

### M5: Quality evaluation (~5 h)
Spec: section 9.
Acceptance: lm-eval command builder snapshot-tested; per-sample parser on provisional `--log_samples` fixture; Wilson and McNemar results on a constructed paired dataset match hand-computed values; agreement check computes exact-match rate and first-divergence position on constructed token sequences; fake-server-based end-to-end test of the agreement check.

### M6: Store and runner (~8 h)
Spec: sections 5.2, 5.4, 11, `store.py`, `runner.py`.
Acceptance: DDL applied exactly as in section 11; whole experiment runs against fake `vllm` and fake `bench` end to end (3 baseline launches + candidates), writes all tables; **resume** after an interrupt (kill mid-experiment in a test) skips completed reps and finishes without duplicates; GPU-hour budget cap aborts cleanly with reason; a `server_failed` launch does not stop the experiment; reps use stored per-rep seeds; schema-version mismatch on open raises a clear error.

### M7: Regression detector and its validation (~8 h)
Spec: section 7.
Acceptance: verdict logic unit-tested at every boundary (effect exactly at threshold, CI straddling, MDE above threshold, <5 reps -> `inconclusive`, direction handling for latency vs throughput); `validate` runs the A/A false-positive test on fake data with injected between-launch noise and reports a count-backed rate; `power` produces the detection-rate-vs-injected-slowdown curve using the fake server (+2/5/10/20%) with fixed seeds and is committed to `reports/power.json`; seeded-regression config recognized by `role` in the output.

### M8: Recommender and report (~7 h)
Spec: section 10, `report.py`.
Acceptance: recommender tested on hand-built data (constraint pass/fail, Pareto set correctness, explanation strings for each rejection); report generated from a fake-server experiment includes: environment block, config table with resolved values, per-workload tables with CI and n, regression verdict table with MDE, quality table with McNemar, agreement table, recommendation with rejected-config reasons, plots (matplotlib, optional extra); the report refuses to print a rate or percentile without its n; every number traces to `stats.py`.

### M9: Live campaign, Qwen3-8B (owner-driven; 8-14 GPU hours + ~6 h)
Not a coding milestone except scripts and fixture replacement. Follow `docs/RUNBOOK_GPU.md` (section 16). Codex deliverables beforehand: `scripts/run_campaign.sh`, `scripts/sync_results.sh`, `docs/RUNBOOK_GPU.md`, `configs/experiment_qwen3_8b.yaml`, resume-safe behavior verified offline. Codex deliverables afterward (owner pastes real logs/JSON): replace every `provisional` fixture with real fixtures, fix parsers against them, rerun the suite.
Acceptance: `reports/` contains the generated report for the real campaign; the DB and raw data are saved off the rented machine; every `provisional` marker is gone or documented.

### M10 (optional): GPT-OSS-120B serving validation (owner-driven; cap 3 GPU hours)
Gate: only after M9's report is committed. Scope: launch `openai/gpt-oss-120b` (documented by vLLM to run on a single A100 with the Triton attention backend and Marlin MXFP4 MoE path; verify on the day), record resolved config and startup log, measure startup time, the maximum feasible `--max-model-len` before OOM (try 8k, 32k, 64k, 128k), server-reported maximum concurrency, and `chat`/`rag` throughput and latency at 1/8/32 concurrency. No claims about 128K usability without a passing measured run at that length. The tool-call parser for this model is a separate setting from Qwen's; not needed here unless testing tool calls. A100 has no native FP4; state that weight-only Marlin is used, so numbers do not predict Hopper/Blackwell behavior.
Acceptance: a short, separate section in the report with its own caveats; failures (OOM, unsupported path) reported as results.

### M11: CI, docs, release (~5 h)
Spec: sections 2, 14. `ci.yml`, `docs/DESIGN.md`, README (quickstart, architecture diagram, results table pasted from `reports/`, limitations), `v0.1.0` tag, SCHEMA frozen.
Acceptance: CI green on a clean clone; `inferencepilot selftest` passes in a fresh virtualenv following the README verbatim (Codex runs it); limitations section includes everything in section 17.

---

## 16. GPU campaign runbook (content for `docs/RUNBOOK_GPU.md`; owner executes)

1. Rent one A100 80GB SXM4 on Vast.ai. Prefer an image that does **not** auto-launch vLLM, or stop the auto-launched server first (check how the `vastai/vllm` template starts it). Use a version tag, not `latest`. Disk 150 GB (Qwen3-8B variants about 16 GB each plus caches; GPT-OSS-120B weights are large, plan another ~65 GB if M10 runs).
2. Install/pin: `pip install vllm==<pinned>` only if the image lacks it; record versions. `pip install -e '.[live]'`.
3. `inferencepilot doctor` must pass (flags verified, `nvidia-smi` works).
4. Load probes for each quantized variant (`inferencepilot probe ...`); decide which variants enter the plan.
5. `inferencepilot plan` then `run --dry-run`; confirm estimated hours within budget; then run inside `tmux` so a dropped SSH session does not kill it. Rented machines can be interrupted or reclaimed: the runner is resume-safe, but sync results off the machine at least every 2 hours (`scripts/sync_results.sh`: rsync/scp of `data/` and the DB).
6. Run order within the session: factor probes, baseline launch 1, candidates (randomized), baseline launch 2, more candidates, baseline launch 3, combined, seeded regression, quality (once per weight/precision variant), agreement check.
7. Before destroying the instance: confirm the DB and `data/raw` are on your own machine, commit real fixtures, then destroy (stopped instances still bill for storage).
8. Back locally: `analyze`, `validate`, `regress`, `recommend`, `report`.

---

## 17. Known risks and honest limitations (copy relevant ones into the README)
1. **Noise.** Server restarts and a shared host add variance. The 3-launch baseline and the MDE exist for this; any comparison smaller than the MDE is `inconclusive`, not "no difference".
2. **Closed-loop vs open-loop.** Concurrency-capped runs measure capacity; they do not represent latency at a given arrival rate. The open-loop stage covers part of this.
3. **Synthetic workloads.** Random-token prompts do not exercise real tokenization/caching behavior; the prefix workload is also synthetic. Say so.
4. **A100 quantization reality.** No native FP8/FP4 compute; quantized variants may be slower or equal and mainly save memory. Present measured results, not expectations.
5. **Quality scope.** One task (gsm8k) via raw completions without chat template or thinking mode measures relative degradation only; it does not generalize to all capabilities.
6. **Version dependence.** All findings are for the pinned vLLM version, one GPU type, one model family. Defaults (prefix caching, chunked prefill) differ across versions.
7. **No interactions beyond the combined candidate.** OFAT misses interactions by design.
8. **Prior art.** vLLM's own benchmark tooling and other load-testing tools exist; InferencePilot's claim is the orchestration, noise-aware comparison, validated detector, paired quality, and recommender, and nothing more.
9. **Schedule risk:** M6 and M7 are the hardest offline milestones; M9 is the cost/time risk. If M9 overruns the budget, reduce reps per point from 5 to 3 only with `inconclusive` verdicts accepted and recorded in `DECISIONS.md`; never silently lower statistical standards.

---

## 18. Session kickoff template

```
Read AGENTS.md fully. Work on Milestone <N>. Restate the acceptance criteria and list the files you will touch before writing code. Follow section 0 (you cannot run a GPU or vLLM). Stop when the milestone's acceptance criteria are met and report per section 0.5. Do not start the next milestone.
```