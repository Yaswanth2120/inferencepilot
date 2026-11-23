# Decisions

## M0 — scope and truthful status

Implement only the M0 package, environment inspection, and fakes. Future
production modules and campaign commands are not empty implementations. The
selftest returns success for CLI wiring but explicitly says the full pipeline
is pending M6. Campaign/report Makefile targets fail instead of pretending to run.

## M0 — fake contract and fixtures

All fake flags are provisional constants in vllm_flags.py. No production flags
are in use yet, so USED_FLAGS is empty; M1 must populate it from real command
builders, pin vLLM, and validate help, including the missing-flag test. Fake
startup logs include a vLLM-shaped engine line and a clearly marked JSON config.
The fake bench generates deterministic arrays rather than implementing a load
generator. Real CLI defaults, full schema, and parsers require M1/M4/M9 validation.
Sources are linked in tests/fixtures/provisional/README.md.

## M0 — determinism and failure controls

A request's delay schedule depends on server seed plus explicit request seed;
therefore repeated requests are reproducible without depending on arrival order.
Concurrency scales delays from the number of active generation requests at entry.
Failure/hang selection uses a separate server-seeded RNG; concurrent failure
assignment consequently follows arrival order. A hang defaults to an hour and
is cancellable; tests shorten it or cancel the request. Synthetic whitespace
tokens intentionally do not simulate any real tokenizer or quality.

## M0 — subprocess ownership

The fake starts one real sleeping child and reaps it on normal shutdown or
SIGTERM. Tests signal the parent alone, assert the child PID disappears, and
use an isolated process group for emergency test cleanup. This validates the
fake itself; production ServerManager safety and teardown remain M3.

## M0 — environment and privacy

Read package versions via distribution metadata, and read CUDA's literal value
from torch/version.py with AST parsing, without executing torch or vLLM.
Record the nvidia-smi driver report separately because its CUDA capability is
not the installed runtime version. Missing information remains null or an
explicit unavailable result. Hash pip freeze rather than storing it, and only
capture the two named Vast identity variables; do not dump the environment.
CPU and RAM inspection have platform fallbacks. No Git repository existed at
kickoff, so a missing SHA is reported rather than inventing provenance.

## M0 — verification boundaries

Local verification uses macOS and Python 3.12.9. CI defines macOS/Linux and
Python 3.10–3.12, but its result is unverified until run on a remote runner.
Real GPU paths: not run (needs GPU). No vLLM pin or novel sweep claim is made
before M1's required release-specific investigation.

## M0 — local virtualenv directory

The workspace repeatedly sets the macOS hidden flag on `.venv` contents;
Python 3.12 skips hidden .pth files, breaking editable imports. Use `venv/`
locally and in the quickstart. Do not mask the failure with PYTHONPATH or
change the subprocess assertions. Both environment directories are gitignored.
