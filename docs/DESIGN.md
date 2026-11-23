# Design through M8

InferencePilot wraps pinned vLLM tooling rather than implementing another load
generator. It compares **tested** configurations with measured noise, paired
quality and an explicit constraint policy. GPU and parser compatibility remain
unverified until the owner supplies M9 evidence.

## Data and execution

Pydantic models validate configurations and plans without I/O. The planner uses
seeded OFAT order, three interleaved independent baseline launches, five reps per
point, a measured-best-level combined candidate, and a role-marked eager candidate.
Unsupported probes retain their records but do not receive scheduled launches.
Optional KV/chunked settings require recorded probe evidence. See
[versioned compatibility research](VLLM_COMPATIBILITY.md).

Runner owns scheduling and external benchmark/harness commands; ServerManager
owns only the server groups it starts. Preflight refuses busy GPUs, occupied ports
and discovered foreign servers. Requested arguments and provisional resolved log
fields are stored separately. Cleanup uses owned groups and bounded TERM/KILL;
foreign processes are never adopted or killed.

Store owns the exact section-11 SQLite DDL, parameterized SQL, WAL/FK settings and
raw artifact paths. A database lock excludes simultaneous runners. A rep row and
logical checkpoint commit atomically. Interrupted slots restart in new physical
server lifetimes while completed logical reps remain attached to their actual
launches. Schema mismatch is explicit; no destructive migration is inferred.

A persisted creation-time deadline bounds launch, benchmark and agreement work,
including time paused before resume. Completed experiments resume as no-ops. The
first measured baseline chat sweep fixes all open-loop arrival rates. Calibration
estimates cover closed-loop work and an explicit extra reserve; open-loop/quality
costs must be reviewed on the actual host. Failed startups remain visible and the
remaining schedule continues.

## Measurement and inference

Loadgen builds argv and parses detailed provisional benchmark JSON. Metrics derives
latencies, physical throughput and configured goodput, cross-checking the tool's
summaries within 1%; failed/partial reps retain raw evidence and counts but do not
enter comparisons. E2E is reconstructed from TTFT plus streaming gaps; token
bundling and real schema compatibility remain documented limitations.

Stats is pure standard-library Python: type-7 percentiles, rep-level bootstrap,
exact/Monte Carlo permutation tests, Holm correction, Wilson, McNemar and a
random-intercept launch-aware MDE. Analysis groups rep values by configuration,
point, metric and physical launch. Regression applies one corrected family per
candidate and reports MDE next to each verdict. Fewer than five reps or MDE above
the decision threshold forces inconclusive.

Quality pins the lm-eval command and aligns logged samples by document/filter and
hashes before paired McNemar. Greedy agreement uses returned token IDs from fixed
raw-completion prompts, never decoded-text stand-ins. Failures stay explicit and
do not fabricate quality or agreement scores.

## Decisions and output

Recommend consumes precomputed statistics. It filters measured SLO/quality evidence,
ranks survivors at a stated throughput objective, retains Pareto choices over
throughput/E2E/quality, and carries MDE/inconclusive evidence into the decision.
Missing evidence rejects a candidate with specific reasons. Ranking is observed
among tested choices, not statistical proof of superiority.

Report renders one shared bundle as Markdown, JSON and optional matplotlib plots.
Mean-of-rep percentiles, bootstrap intervals and replication counts are labelled;
rates/percentiles without positive counts cannot render. Raw paths point into the
archived DB/data capture; persisted summaries support analysis after transfer.
Regression re-analysis replaces prior rows atomically, while recommendations retain
an execution history.

## Offline and live boundary

Fakes are an explicit dev package and are never imported by production modules.
Selftest delegates into that package in a child process. It starts six fake servers,
saves 120 reps, checks idempotent resume, and fills every schema table through the
full quality, regression, A/A, recommendation and report pipeline. A synthetic
unsupported candidate exercises rejected-config reasons. Separate tests interrupt
a runner subprocess and verify checkpoint identities and seeds after resume.

Power uses seeded fake HTTP timing responses and reports actual detection counts;
it is a simulated timing-model result, not a GPU claim. The campaign wrapper,
calibration helper and WAL-safe backup script are prepared and tested offline.
The owner follows [RUNBOOK_GPU.md](RUNBOOK_GPU.md) for M9; real fixtures and live
findings are **not run (needs GPU)**. M10/M11 and the release tag remain separate gates.
