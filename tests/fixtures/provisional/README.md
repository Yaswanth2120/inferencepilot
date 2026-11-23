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
