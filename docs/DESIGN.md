# Design status

M0 implements package wiring, environment inspection, and isolated fakes.
M1 adds data-only Pydantic models, a pure deterministic planner, declarative
flag mappings, and CLI handlers for plan files and dry-run output. Production
modules do not import the fake package or vLLM.

The planner builds seven standard OFAT candidates, a deferred combined
candidate, the eager seeded regression, and three independent baseline launch
slots. It stores seeds and workload points; future M6 execution owns process
starts, warmups, checkpoints, and budget enforcement. Missing probes remain
pending; unsupported probes keep their evidence in the configuration table.

The combined candidate must be selected from measured individual results.
It has no ConfigSpec before that selection and cannot honestly have an argv.
Its launch slot uses the same calibration estimate as other slots. A failed
baseline probe prevents a plan. Unknown open-loop capacity is explicitly
deferred to M4/M6 and excluded from the current estimate.

Plan JSON excludes timestamps and output paths. Its stable sorted serialization
is reproducible for identical input and seed. Dry-run reconstructs the plan
from its embedded experiment and rejects edited or stale derived fields.
See DECISIONS.md for the baseline-order ambiguity and cost formula, and
VLLM_COMPATIBILITY.md for versioned sources and overlap with existing tools.
