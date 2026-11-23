# Configuration

`experiment_qwen3_8b.yaml` is a validated M1 planning example with all eight
closed-loop workload points. Its calibration numbers are explicitly synthetic,
its quantized variants require load probes, and its combined candidate is
unresolved. It is not ready to launch a live GPU campaign.

Record measured per-rep calibration seconds under workload@concurrency keys,
plus startup, teardown, and an explicit quality/other reserve. Calibration
rep durations exclude warmups; the planner reserves proportional warmup time.
`extra_seconds` is a budget reserve, not a measurement or automatic scheduler.
A measured source must include a note identifying the calibration evidence.

Optional chunked-prefill-off and FP8 KV factors need entries in `probes` with
status `supported` or `unsupported_on_hardware` and nonempty evidence text.
Those entries will be produced from actual probes in M3/M9; never fabricate them.
Unsupported variants remain in plan.configs with evidence and are omitted from
scheduled launches. Missing weight probes are marked pending, never supported.
