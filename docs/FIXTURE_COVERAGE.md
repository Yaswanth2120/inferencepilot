# Fixture coverage after the live Qwen campaign

M9 verified the pinned vLLM 0.15.1 / lm-eval 0.4.9.2 interfaces against real startup,
detailed benchmark and sample logs. Generic `parser_status="provisional"` markers
remain conservative because a parser cannot infer software-version compatibility
from arbitrary input. They do not mean the committed real measurements are synthetic.

| Source / marker | Evidence and reason retained |
|---|---|
| `real/qwen3_vllm_0151_startup.log` | Measured BF16 startup: readiness, prefix/chunk settings, cache capacity and CUDA graph mode. |
| `real/qwen3_{fp8_online,fp8_ckpt,eager,combined}_startup.log` | Measured campaign starts: precision, prefix state, token budget, eager and resolved graph mode tested offline. Trailing whitespace trimmed; ANSI retained. |
| `real/qwen3_vllm_0151_prefix64.json.gz` | Unchanged full detailed result, 200 requests; raw summary cross-checks pass. The complete archive contains all 605 campaign reps and was re-parsed locally. |
| `real/qwen3_lmeval_0492_samples.jsonl` | First-16 commissioning sample fields from both filters; hashes and correctness unchanged. The archived campaign has full first-200 samples for four independent evaluations. |
| `provisional/startup.log`, `startup_full.log` | Synthetic formatting and controlled resolved-value edge cases remain useful; real fixtures augment rather than replace them. |
| `provisional/bench.json`, `bench_worked.json` | Small hand-computed and failure/truncation cases exercise metrics and adapter errors absent from the successful campaign. They remain explicitly synthetic. |
| `provisional/bench_commands.json` | Command snapshots validate construction; executable `doctor` verified all used flags on the pinned live installation. A command snapshot is not live evidence. |
| `provisional/gsm8k_samples.jsonl` | Constructed paired correctness/hashes validate statistical edge cases independently of the observed results. |
| Fake server / benchmark outputs | Intentionally provisional-shaped synthetic data, never a substitute for measured GPU performance or model quality. |
| `reports/qwen3-20261125/report.*` parser notes | Original generated notes are preserved; this document narrows which observed interfaces have real coverage. No unsupported-version compatibility claim is made. |

AWQ's requested forced-`awq`/BF16 rejection is preserved in the published probe
JSON with its startup error. It is a software/dtype incompatibility for that request,
not proof that A100 cannot run AWQ. No FP16 or Marlin-AWQ substitution was measured.

Chunked prefill remained on and KV cache dtype remained auto; their alternative
factor levels were not evaluated. Startup OOM/hang/port-conflict/child-teardown
failures still have offline fake coverage rather than fabricated live examples.
Future vLLM versions, other GPUs, optional factors and context-boundary cases remain
unverified. Unrun optional GPU paths: **not run (needs GPU)**.
