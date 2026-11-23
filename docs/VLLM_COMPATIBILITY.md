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
it does not proceed to start a server. M4 must add its benchmark flags to
USED_FLAGS when it introduces the production benchmark command builder.
The fake version string labels itself fake and does not establish real compatibility.

Config validation follows the pinned [scheduler implementation](https://github.com/vllm-project/vllm/blob/v0.15.1/vllm/config/scheduler.py):
token budget must cover the sequence ceiling and, with chunked prefill off,
the maximum model length. Presence of an option does not prove hardware support
or that the engine honors it; M3/M9 probes and resolved logs remain required.
