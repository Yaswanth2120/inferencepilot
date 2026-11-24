# GPT-OSS existing-server performance validation

completed

Existing server observed, never restarted; one server lifetime, no between-launch MDE or config-regression claims.
Raw-completion synthetic performance only; no chat-template, reasoning-quality or GSM8K claims.
Only the advertised context limit is verified. Higher context limits, OOM boundary and startup time: not run (needs GPU restart).
User explicitly selected the preinstalled GPT-OSS model and vLLM version instead of the gated Qwen/pinned-version campaign.

| Point | Metric | Mean | 95% CI | n reps |
|---|---|---|---|---|
| chat:closed:1 | request_throughput | 0.636648 | [0.636167, 0.636958] | 5 |
| chat:closed:1 | output_throughput | 162.982 | [162.859, 163.061] | 5 |
| chat:closed:1 | p95_e2e | 1573.97 | [1572.17, 1577.3] | 5 |
| chat:closed:1 | p95_itl_pooled | 6.37106 | [6.32903, 6.39493] | 5 |
| chat:closed:1 | p95_tpot_per_request | 5.95513 | [5.9544, 5.95586] | 5 |
| chat:closed:1 | p95_ttft | 56.8703 | [55.1811, 59.7868] | 5 |
| rag:closed:1 | request_throughput | 0.478438 | [0.478188, 0.478645] | 5 |
| rag:closed:1 | output_throughput | 122.48 | [122.416, 122.533] | 5 |
| rag:closed:1 | p95_e2e | 2099.42 | [2098.1, 2101.16] | 5 |
| rag:closed:1 | p95_itl_pooled | 6.86009 | [6.82865, 6.88416] | 5 |
| rag:closed:1 | p95_tpot_per_request | 6.4985 | [6.49736, 6.49943] | 5 |
| rag:closed:1 | p95_ttft | 449.008 | [447.49, 450.823] | 5 |
| chat:closed:8 | request_throughput | 0.637942 | [0.637663, 0.638221] | 5 |
| chat:closed:8 | output_throughput | 163.313 | [163.242, 163.384] | 5 |
| chat:closed:8 | p95_e2e | 12569.1 | [12542.3, 12595.9] | 5 |
| chat:closed:8 | p95_itl_pooled | 6.33169 | [6.32067, 6.34535] | 5 |
| chat:closed:8 | p95_tpot_per_request | 5.96323 | [5.95568, 5.97723] | 5 |
| chat:closed:8 | p95_ttft | 11052 | [11024.7, 11079.4] | 5 |
| rag:closed:8 | request_throughput | 0.483366 | [0.483204, 0.483527] | 5 |
| rag:closed:8 | output_throughput | 123.742 | [123.7, 123.783] | 5 |
| rag:closed:8 | p95_e2e | 16590.7 | [16576.8, 16606.7] | 5 |
| rag:closed:8 | p95_itl_pooled | 6.92224 | [6.89191, 6.95526] | 5 |
| rag:closed:8 | p95_tpot_per_request | 6.49417 | [6.49171, 6.49655] | 5 |
| rag:closed:8 | p95_ttft | 14937.6 | [14924.8, 14953.2] | 5 |
| chat:closed:32 | request_throughput | 0.637888 | [0.637743, 0.638033] | 5 |
| chat:closed:32 | output_throughput | 163.299 | [163.262, 163.336] | 5 |
| chat:closed:32 | p95_e2e | 50181 | [50159.8, 50204.4] | 5 |
| chat:closed:32 | p95_itl_pooled | 7.07568 | [6.72915, 7.3589] | 5 |
| chat:closed:32 | p95_tpot_per_request | 5.96558 | [5.95812, 5.97507] | 5 |
| chat:closed:32 | p95_ttft | 48662 | [48640.7, 48686.4] | 5 |
| rag:closed:32 | request_throughput | 0.483053 | [0.483003, 0.483113] | 5 |
| rag:closed:32 | output_throughput | 123.662 | [123.649, 123.677] | 5 |
| rag:closed:32 | p95_e2e | 66362.2 | [66333.4, 66393.7] | 5 |
| rag:closed:32 | p95_itl_pooled | 7.21114 | [6.99984, 7.46845] | 5 |
| rag:closed:32 | p95_tpot_per_request | 6.50156 | [6.49606, 6.5108] | 5 |
| rag:closed:32 | p95_ttft | 64708.4 | [64680, 64739.5] | 5 |

Excluded reps: `[]`

## Observed configuration

```json
[
  {
    "context_limit_source": "/v1/models; not an OOM search",
    "host": "127.0.0.1",
    "max_model_len": 8192,
    "model": "openai/gpt-oss-120b",
    "observed_model": {
      "created": 1795537231,
      "id": "openai/gpt-oss-120b",
      "max_model_len": 8192,
      "object": "model",
      "owned_by": "vllm",
      "parent": null,
      "permission": [
        {
          "allow_create_engine": false,
          "allow_fine_tuning": false,
          "allow_logprobs": true,
          "allow_sampling": true,
          "allow_search_indices": false,
          "allow_view": true,
          "created": 1795537231,
          "group": null,
          "id": "modelperm-a6f7bac431e9cd47",
          "is_blocking": false,
          "object": "model_permission",
          "organization": "*"
        }
      ],
      "root": "openai/gpt-oss-120b"
    },
    "ownership": "external",
    "port": 18000
  }
]
```

## Environment

```json
{
  "cpu": "AMD EPYC 7513 32-Core Processor",
  "cuda_driver_report": {
    "available": true,
    "output": "Tue Nov 24 16:20:46 2026       \n+-----------------------------------------------------------------------------------------+\n| NVIDIA-SMI 595.91.07              Driver Version: 595.91.07      CUDA Version: 13.2     |\n+-----------------------------------------+------------------------+----------------------+\n| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |\n| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |\n|                                         |                        |               MIG M. |\n|=========================================+========================+======================|\n|   0  NVIDIA A100-SXM4-80GB          On  |   00000000:41:00.0 Off |                    0 |\n| N/A   25C    P0             71W /  400W |   72495MiB /  81920MiB |      0%      Default |\n|                                         |                        |             Disabled |\n+-----------------------------------------+------------------------+----------------------+\n\n+-----------------------------------------------------------------------------------------+\n| Processes:                                                                              |\n|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |\n|        ID   ID                                                               Usage      |\n|=========================================================================================|\n|  No running processes found                                                             |\n+-----------------------------------------------------------------------------------------+"
  },
  "cuda_runtime_note": "read from torch/version.py without importing torch; null if unavailable",
  "cuda_runtime_version": "13.0",
  "git": {
    "available": true,
    "output": "f0c109c448c315eea57993b984d402d91c9872dd"
  },
  "gpu": {
    "available": true,
    "output": "NVIDIA A100-SXM4-80GB, 8.0, 595.91.07"
  },
  "lm_eval_version": null,
  "pip_freeze_sha256": "ccbe25c7483bea9dad043548b68a934a0a7e088bfdab5d9e5e21f383a276f37d",
  "platform": "Linux-6.8.0-138-generic-x86_64-with-glibc2.39",
  "python": "3.12.3",
  "ram_bytes": 540590342144,
  "torch_version": "2.13.0+cu130",
  "vast": {
    "VAST_CONTAINERLABEL": "<redacted; original retained in local archive>"
  },
  "vllm_version": "0.32.0"
}
```

## Completion and provenance

30/30 reps passed: 3,000 requests and 768,000 output tokens. Elapsed benchmark time: 108.4 minutes. All 30 archived raw files were re-parsed and cross-checked locally. The off-machine SQLite backup passed integrity_check.

Actual max_num_seqs=1; concurrency 8/32 measured queueing behind that scheduler limit. Requested concurrency is not realized batching. The exact deployed source hashes are in report.json because the captured git SHA was the base checkout before the tested working-tree changes were copied.
