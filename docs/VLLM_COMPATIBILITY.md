# vLLM compatibility and prior art

M1 pins **vLLM 0.15.1** as the reproducible interface target. This is a deliberate
versioned target with documentation for required features, not a claim to use
the newest release. Neither vLLM nor a GPU was installed or run for M1.
A future pin change requires updated constants, doctor checks, fixtures, and docs.

The versioned [sweep guide](https://docs.vllm.ai/en/v0.15.1/benchmarking/sweeps/)
shows that `vllm bench sweep serve` already launches servers over parameter
combinations, repeats benchmark runs, supports resume, and has SLA tuning and
visualization tools. Server lifecycle, sweeps, repetitions, resume, and SLA
search are therefore **not novel contributions** of InferencePilot.

InferencePilot's intended focus is independent baseline launches placed to
expose drift, rep-aware statistical comparisons with a stated MDE, multiple-test
correction, measured false-positive rate/power, paired quality checks, and a
constraint-based recommendation that reports uncertainty. Those statistics,
validation, and quality features are later milestones; M1 implements design only.
We make no claim that every other tool lacks comparable features.

## Flag contract

The [serve reference](https://docs.vllm.ai/en/v0.15.1/cli/serve/) documents
positive and negative prefix-caching/chunked-prefill switches and the token,
sequence, dtype, quantization, context, memory, port, and seed options.
The [benchmark reference](https://docs.vllm.ai/en/v0.15.1/cli/bench/serve/)
documents detailed results and warmup controls for the future M4 adapter.
All flag spellings and the ConfigSpec mapping live in `vllm_flags.py`.

Doctor checks the selected binary's version and every serve flag currently
used by ConfigSpec. It requests the full help because the pinned parser's
[implementation](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/utils/argparse_utils.py)
provides grouped help by default. A missing flag fails the environment check;
it does not proceed to start a server. M4 registers all benchmark flags in USED_FLAGS alongside serve flags; doctor
now checks both complete help outputs.
The fake version string labels itself fake and does not establish real compatibility.

Config validation follows the pinned [scheduler implementation](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/config/scheduler.py):
token budget must cover the sequence ceiling and, with chunked prefill off,
the maximum model length. Presence of an option does not prove hardware support
or that the engine honors it; M3/M9 probes and resolved logs remain required.


## M4 detailed-result contract

The implementation was inspected directly at the pinned tag:
[serve metrics and serialization](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/benchmarks/serve.py),
[completion timing](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/benchmarks/lib/endpoint_request_func.py),
and [dataset arguments](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/benchmarks/datasets.py).
The source exports per-request input/output lengths, TTFT, streaming gaps, and
errors, but not individual E2E values. E2E is reconstructed and checked against
the reported p99; the separate first-token clock readings can introduce skew.
Only openai raw completions are supported; chat timing has different semantics.

A stream gap is not assumed to equal one output token. The exported output
count comes from usage or tokenization; TPOT divides total decode time by
output_tokens-1. Required numeric fields and arrays are validated strictly;
unused metadata is ignored rather than treated as another timing authority.
The command explicitly enables E2E summaries because the generative default
percentile list omits E2E. Warmups are unmeasured and do not appear in arrays.
Main-pipeline vLLM 0.15.1 compatibility remains provisional until M9 evidence.
A separate GPT-OSS vLLM 0.32.0 raw-completion fixture and 30-rep serving run were
verified on 2026-11-24; this does not certify the pinned lifecycle or quality path.
