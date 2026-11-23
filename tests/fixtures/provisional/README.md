# Provisional fixtures

These are fake outputs, not observations of real vLLM. `bench.json` was generated
by the fake executable with its default lengths and seed 7; `startup.log` is a
small constructed example of its startup shape. M9 must replace or explicitly
document these provisional artifacts after receiving actual campaign output.

The interface is informed by the official [benchmark CLI guide](https://docs.vllm.ai/en/stable/benchmarking/cli/)
and [serve benchmark arguments](https://docs.vllm.ai/en/stable/cli/bench/serve/).
The engine log shape follows the documented [engine initialization source](https://docs.vllm.ai/en/v0.21.0/api/vllm/v1/engine/core/).
No exact vLLM release compatibility is claimed. M1 must select a release and
check its help and sweep capabilities before building the real planner.


M3 adds `startup_full.log`, a constructed engine/scheduler/KV/backend/graph log
for parser tests. Its shapes are informed by the versioned
[parallelism guide](https://docs.vllm.ai/en/v0.15.0/serving/parallelism_scaling/)
and [CUDA graph design](https://docs.vllm.ai/en/v0.15.1/design/cuda_graphs/).
No part of it is a captured 0.15.1 GPU startup log. M9 must replace it with real
owner-provided output or document every remaining provisional field.


M4 refreshes `bench.json` to the consumed v0.15.1 detailed generation schema:
backend/counts and TTFT/gap arrays, with no invented per-request E2E array.
`bench_worked.json` is a hand-constructed three-request example, including bundled
stream gaps, with independently worked metric expectations in tests.
`bench_commands.json` contains exact expected argv for all eight configured
closed-loop points and three open-loop chat rates. These are contract snapshots,
not commands captured from a real campaign. Pinned source links are in
`docs/VLLM_COMPATIBILITY.md`; M9 must replace/document provisional result fixtures.
