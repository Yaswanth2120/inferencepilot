# Real GPT-OSS smoke fixture

`gptoss_vllm_032_smoke.json` was captured on 2026-11-24 from the owner-authorized
single A100-SXM4-80GB instance: vLLM 0.32.0, `openai/gpt-oss-120b`, MXFP4, existing
8k-context server with max_num_seqs=1. Three raw completion requests used 8 input
and 4 fixed output tokens, seed 42, concurrency 1 and one warmup. Generated text
was removed; measurement arrays and tool summaries are unchanged. No keys/tokens
are included. This validates that specific result schema, not all software versions,
chat quality, long contexts, or independently replicated server launches.
