# Real live fixtures

`qwen3_vllm_0151_startup.log` was captured during the owner-authorized M9 baseline
calibration on 2026-11-24 (local date; remote logs use UTC on November 25).
It records Qwen/Qwen3-8B BF16 on one A100-SXM4-80GB, vLLM 0.15.1, through successful
health and model-list responses. The fixture is the owned startup log prefix through readiness, with ANSI escapes
retained and trailing whitespace trimmed. Tests verify resolved settings, CUDA graph
mode, attention backend and KV cache/concurrency values. This establishes baseline
startup parsing only; provisional failure/quantization cases remain until their
own real evidence exists. It does not establish campaign completion or model quality.

`qwen3_vllm_0151_prefix64.json.gz` is the complete, unchanged detailed JSON from
the baseline prefix calibration at concurrency 64: 200 requests, 128 output tokens
each, no failures. Gzip uses a zero timestamp for reproducibility; the decompressed
SHA-256 is `254a571c44b9a6938eeea5e787bedb6b0659b19202c9e68ce60a63b1aa7a98d2`.
Its original request arrays and summaries pass the adapter's 1% cross-checks.

`qwen3_lmeval_0492_samples.jsonl` retains document/prompt hashes, filter identities
and correctness from all 16 first-N pilot problems (32 filter rows), using harness
0.4.9.2, five-shot raw completions. Problem text, prompts and generated text were
removed; retained fields are unchanged. Both filters scored 14/16. This small
commissioning subset establishes parser compatibility, not campaign quality.

Provisional edge cases remain intentionally documented: synthetic failure/truncation
arrays, unobserved startup failures and quantized log formats, and constructed
paired correctness changes still exercise behaviors absent from these real samples.
The generic parser markers remain conservative until the full campaign review.

## GPT-OSS smoke

`gptoss_vllm_032_smoke.json` was captured on 2026-11-24 from the owner-authorized
single A100-SXM4-80GB instance: vLLM 0.32.0, `openai/gpt-oss-120b`, MXFP4, existing
8k-context server with max_num_seqs=1. Three raw completion requests used 8 input
and 4 fixed output tokens, seed 42, concurrency 1 and one warmup. Generated text
was removed; measurement arrays and tool summaries are unchanged. No keys/tokens
are included. This validates that specific result schema, not all software versions,
chat quality, long contexts, or independently replicated server launches.

## Completed campaign extension

`qwen3_fp8_online_startup.log`, `qwen3_fp8_ckpt_startup.log`,
`qwen3_eager_startup.log` and `qwen3_combined_startup.log` are actual campaign
startup prefixes through readiness, with trailing whitespace trimmed and ANSI
retained. Offline tests assert their precision, prefix setting, token budget,
eager setting and resolved CUDA graph mode. They add coverage to the existing
baseline/benchmark/harness fixtures. See [coverage](../../../docs/FIXTURE_COVERAGE.md)
for the exact purpose of every retained provisional source and marker.
