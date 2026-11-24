# Owner-selected GPT-OSS validation — 2026-11-24

Status: live smoke passed; the 30-rep serving benchmark was launched and is **in progress**.
This is not a completed Qwen campaign or an independent-launch regression study.

Observed hardware/software:

- One NVIDIA A100-SXM4-80GB (81920 MiB reported capacity).
- vLLM 0.32.0, Torch 2.13.0+cu130, driver 595.91.07.
- Existing `openai/gpt-oss-120b` server; MXFP4 with MARLIN MoE and TRITON_ATTN.
- Advertised max context 8192; startup arguments record max_num_seqs=1.
- Raw-completion synthetic performance, not chat-template/reasoning/GSM8K quality.

The measured smoke used three requests at concurrency 1, input/output 8/4 tokens,
one warmup and seed 42. All three succeeded; our raw-derived means/percentiles and
throughput passed the tool-summary cross-check, including agreement with the direct
latency array. Its sanitized complete timing fixture is at
`../../tests/fixtures/real/gptoss_vllm_032_smoke.json`. It supports that schema/sample,
not broad performance or compatibility claims.

The longer benchmark targets chat 256/256 and RAG 4096/256, client concurrency
1/8/32, 100 measured prompts per rep, ten warmups and five fixed-seed reps per point.
Because the server's scheduler permits only one sequence, higher client concurrency
measures queueing under that configured limit. A three-hour cap bounds benchmarking;
only owned benchmark subprocesses may be stopped. The existing model server stays
running, and rental billing is not automatically stopped.

Runtime artifacts on the host: `/workspace/inferencepilot/data/gptoss-20261124/`.
Supervisor job: `inferencepilot_gptoss_20261124` (no automatic restart).
Experiment: `23f3596e2513447cb40f8ea57ff0d016`.
Progress is in `status.json`, completed reps in `experiment.db`, raw arrays/logs in
`raw/`, and terminal reports in `reports/`. Local off-machine captures are under
the gitignored `data/live/gptoss-20261124/archive/` directory. A local background
pull checks every minute while the Mac is awake/connected, using SQLite's backup
API before transfer. Do not destroy the rental before checking the final archive.

Startup time, restarted configurations, context/OOM boundary above 8192, independent
launch noise, the Qwen campaign and paired model-quality comparisons: **not run
(needs GPU)**. Final benchmark aggregates will be published after checking the
terminal status and archived DB. No v0.1.0 release claim is made.
