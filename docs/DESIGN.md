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


M3 adds ServerManager and persistent probe output. The manager returns a
LaunchResult; M6 will map it into SQLite rather than introducing SQL early.
It owns only a Popen-created group, retains that ownership through failed
cleanup, and clears it only after read-only inspection finds no active group
members. The parent is reaped before closing logs and checking memory release.
An unknown process state or memory result fails closed.

Pure startup parsing lives with server lifecycle. Last matching resolved values
win and matched raw lines remain attached. Missing keys stay missing; parser
status remains provisional. The probe module compares requested vs observed
factor values and stores failure evidence independently of the future runner.
No production module imports fakes. GPU telemetry around benchmark reps is
still a future runner responsibility; no rep execution is added in M3.
