# GPU campaign runbook

The [completed Qwen3 campaign](../reports/qwen3-20261125/README.md) contains the
measured results and archive verification. This runbook supports reproducing that
workflow; rental provisioning and billing shutdown remain manual. Optional GPT-OSS
cold-start/context tests are **not run (needs GPU)** and outside v0.1.0.

## Rental and setup

Use the project's specified **one NVIDIA A100 80 GB SXM4**, with at least **150 GB disk**,
SSH access, and a pinned CUDA-compatible image that does not auto-launch vLLM. Plan
from measured calibration, plus installation/download time. The completed full
performance/first-200-quality run used an approved 22-hour cap and completed in
19.51 workflow hours including interruption and analysis. The default remains
14 hours; explicitly review the plan and budget before starting. That wall-clock
cap starts at experiment creation, not rental, and includes paused time.
Check the provider's actual hourly and storage prices before purchasing. Do not use
multiple GPUs. Keep optional GPT-OSS work out of this Qwen campaign.

On the host, clone the public repository and activate a Python 3.10–3.12 virtualenv:

```sh
git clone https://github.com/Yaswanth2120/inferencepilot.git
cd inferencepilot
python3 -m venv venv
source venv/bin/activate
python -m pip install 'vllm==0.15.1'
python -m pip install -e '.[live,report]'
inferencepilot doctor
```

Use an image whose existing Torch/CUDA matches vLLM's pinned distribution. If doctor
fails, capture its output and fix the environment before benchmarking. Confirm the
GPU is idle. Do not kill unknown processes automatically; identify template-owned
servers and stop those through their documented owner mechanism.

## Probes and calibration

Record load probes on the rented hardware. BF16 must pass; each quantized failure
is evidence, not a reason to assume its results or silently discard the variant:

```sh
inferencepilot probe --model Qwen/Qwen3-8B --variant bf16 --out data/probes/bf16.json
inferencepilot probe --model Qwen/Qwen3-8B --variant fp8_online --out data/probes/fp8_online.json
inferencepilot probe --model Qwen/Qwen3-8B-AWQ --variant awq --out data/probes/awq.json
inferencepilot probe --model Qwen/Qwen3-8B-FP8 --variant fp8_ckpt --out data/probes/fp8_ckpt.json
python scripts/calibrate.py --config configs/experiment_qwen3_8b.yaml --out data/measured.yaml
```

A failed probe exits 3. Inspect its stored launch errors: a preflight/environment
failure is not proof of hardware incompatibility. Fix that cause and rerun with a
fresh output path. For a confirmed model load failure, set its ProbeEvidence status
to `unsupported_on_hardware`; retain the JSON/log path in `evidence`. For a passing
probe use `supported`. Add these records to `data/measured.yaml` under `probes`:

```yaml
probes:
  bf16:
    status: supported
    evidence: data/probes/bf16.json
```

Include all four weight variants with their actual classifications. Optional chunked
prefill/KV factors require their own probes and resolved-setting verification first.
A100 has no native FP8 compute; the pinned vLLM table lists Marlin support on Ampere,
but it does not guarantee every Qwen checkpoint loads. See the
[pinned quantization matrix](https://docs.vllm.ai/en/v0.15.1/features/quantization/).

Calibration measures one baseline rep at each configured closed-loop point and
stores detailed raw results. Its one-hour extra reserve is a starting allowance
for quality and open-loop work, not a measured duration for either. Review and
increase it when necessary. Never relabel the committed synthetic table as measured.
The combined candidate is selected only after individual levels are measured.

## Run, monitor, resume

```sh
inferencepilot plan --config data/measured.yaml --out data/plan.json
scripts/run_campaign.sh data/plan.json data/campaign.db
# Review estimate, supported variants, storage, and the 14-hour cap before execution.
tmux new -s inferencepilot
scripts/run_campaign.sh data/plan.json data/campaign.db --execute
```

The wrapper previews by default and refuses live execution with synthetic calibration,
pending probes, or an over-budget estimate. `--execute` runs doctor first and uses
`configs/constraints.yaml` for request-level goodput thresholds. Keep console output:
it includes the experiment ID. If interrupted before the ID prints, inspect it read-only:

```sh
python -c "import sqlite3; print(sqlite3.connect('data/campaign.db').execute('SELECT id,status,abort_reason FROM experiments').fetchall())"
inferencepilot status --db data/campaign.db --experiment ID
inferencepilot resume --db data/campaign.db --experiment ID
```

SIGTERM/SIGINT clean up owned server/benchmark groups. SIGKILL, machine loss, and a
lost shell cannot guarantee cleanup; inspect running processes first. The runner
will not adopt or kill a surviving foreign server. Completed reps keep their
original physical launch ID and are skipped on resume. An interrupted launch is
restarted with a new ID. Paused time still consumes the original wall-clock cap.
Schema incompatibility is an error, not an automatic destructive migration.

## Backups and analysis

At least every two hours, and before destroying the instance, run on the GPU host:

```sh
scripts/sync_results.sh data/campaign.db data OWNER@BACKUP_HOST:/absolute/path/inferencepilot-backup
```

Supply your own configured SSH destination or mounted off-machine directory. The
script uses SQLite's backup API and checks database integrity before rsync; copying
only the live `.db` could omit WAL checkpoints. It never deletes destination files.
The backup contains `experiment.db` plus `data/raw`, logs, plans and probes. Raw paths
in SQLite refer to the capture host; keep this archive intact and remap paths only
on a separate analysis copy if necessary. Reports use persisted summaries, so they
can render after moving the database without pretending raw files were reread.
Verify the backup with `PRAGMA integrity_check`, inspect raw/log counts, and retain
checksums locally. Also copy reports and the environment snapshot. Then run:

```sh
inferencepilot analyze --db data/campaign.db --experiment ID
inferencepilot validate --db data/campaign.db --experiment ID
inferencepilot regress --db data/campaign.db --experiment ID --baseline baseline
# regress exits 1 for a finding; preserve its evidence and continue analysis explicitly.
inferencepilot recommend --db data/campaign.db --experiment ID --constraints configs/constraints.yaml
inferencepilot report --db data/campaign.db --experiment ID --out reports/qwen3-live
```

Do not claim the eager candidate regressed unless corrected comparisons support it;
report inconclusive MDEs honestly. Export small real detailed benchmark, startup-log,
and harness samples for replacing provisional fixtures. Preserve hashes/provenance,
remove identifying prompt content where needed, and share the real logs/JSON for
parser verification. A successful offline test is not live parser compatibility.

Destroy the instance only after verifying the external backup. Stopping alone keeps
storage billing active, and destruction permanently removes instance data; see
[Vast's billing guidance](https://github.com/vast-ai/docs/blob/main/guides/reference/faq/billing.mdx).
M9 is complete only after real evidence and fixture checks are committed. M10 remains
optional and M11 release work follows; M8 completion is not a v0.1.0 release claim.

## Detached automation across an assistant usage reset

Run the following **on the GPU host**, after setup, probes, measured calibration,
and plan review. It uses the active virtualenv and starts an independent process
session; it does not depend on Codex tokens, an open SSH connection, or tmux.

```sh
python scripts/detached_campaign.py start \
  --plan data/plan.json --db data/campaign.db \
  --state-dir data/jobs/qwen3-first --max-hours 5
```

Five hours is an explicit example cap, not a promise the full campaign will fit.
The supervisor deadline includes doctor, the campaign and analysis. It also passes
the cap to the runner. Cleanup and a final bounded backup can take additional time.
If the cap expires, saved reps remain available but the report stage may not run;
continue later by resuming or analyzing the saved database. A job cap stops workload
processes; **it does not stop billing or destroy the rental instance**.

The command returns a worker PID, log path and status path. The worker runs doctor,
then run/resume, analyze, validate, regress, recommend and report. A regression exit
code 1 is retained as a finding and does not suppress the report. Other failed
stages stop the workflow with an explicit error. There is no blind crash/reboot
retry: inspect errors and process ownership before an explicit resume.

```sh
python scripts/detached_campaign.py status --state-dir data/jobs/qwen3-first
tail -n 80 data/jobs/qwen3-first/worker.log
```

`status.json` contains the experiment ID as soon as the DB has it, phase, deadline,
PID, stage exit codes, backup history and terminal error/status. Reports are under
`data/jobs/qwen3-first/reports/`. The plan/options are saved in `job.json`. Use a
fresh state directory for each attempt. To resume a saved experiment:

```sh
python scripts/detached_campaign.py start \
  --plan data/plan.json --db data/campaign.db --resume EXPERIMENT_ID \
  --state-dir data/jobs/qwen3-resume --max-hours 5
```

The runner retains its original deadline; resuming does not replenish that budget.
If an experiment exhausted its cap, inspect the saved evidence and choose the next
scope explicitly rather than relabelling it completed or silently raising its cap.

For hourly off-machine backups, configure noninteractive SSH authentication from
the GPU host to an owner-controlled destination and append:

```sh
--backup-to OWNER@BACKUP_HOST:/absolute/path/inferencepilot-backup --backup-seconds 3600
```

Without `--backup-to`, results stay on the GPU host; no external backup is implied.
Backup failures are recorded in status and logs while the campaign continues. Test
the destination first. For the documented state directory under `data/`, DB backup,
raw artifacts, job logs/status and completed reports are all included. Keep backup
destinations outside the source data directory. Machine reclamation or reboot can
still stop the detached worker; a detached process is not persistent cloud storage.

When assistant usage is available again, return with the SSH details and state
path. The assistant can reconnect, inspect status, fetch the DB/raw/report archive,
and finish analysis if needed. A usage reset does not automatically wake an
assistant or trigger a reconnection. No automatic rental shutdown is configured.

## Owner-selected existing GPT-OSS server

The 2026-11-24 owner instruction selected the installed GPT-OSS-120B model instead
of the Qwen-first sequence. `scripts/benchmark_existing.py` is a separate read-only
server-attachment workflow. It validates `/v1/models`, checks the installed bench
flags, measures chat/RAG at client concurrency 1/8/32 with five reps and checkpoints
raw results. It does not start/restart/stop the existing model service, change its
context, or weaken the Qwen ConfigSpec model restrictions.

```sh
python scripts/benchmark_existing.py --db data/gptoss-20261124/experiment.db \
  --model openai/gpt-oss-120b --port 18000 --hours 3 --prompts 100
```

Resume adds `--resume EXPERIMENT_ID` with unchanged arguments and retains the old
deadline. Use a managed Supervisor job on the current Vast image for independent
execution; autorestart must stay disabled to avoid uncontrolled benchmark retries.
Capture the existing startup log separately and never relabel observation time as
startup time. Report one physical server lifetime, unknown startup duration and
untested context limits explicitly. A pre-existing max_num_seqs=1 means client
concurrency 8/32 measures serialization/queueing, not useful batching. Raising this
or testing larger context requires a separately authorized server restart.

The main Qwen version pin remains 0.15.1. The owner-selected installed server is
0.32.0, with its own real fixture; successful measurement here is not a pass for the
pinned-version doctor or every provisional fixture. See the live validation note
for checkpoint, archive and Supervisor paths. Stopping this benchmark does not stop
the model server or rental billing.

## Shared-instance access and provenance

Coordinate access before using a shared GPU. Offline tests and release verification
require neither SSH nor a rental. Never stop foreign workloads or alter a shared
Python environment; use a separate checkout and virtualenv when appropriate.

Future direct campaign execution can declare `--evidence live`; run_campaign.sh
and the detached supervisor add this declaration automatically for an explicitly
started campaign. Direct runs default to unverified. Existing DBs without a
saved declaration remain unverified rather than being relabelled from GPU/model
metadata. Keep synthetic tests explicitly synthetic. Provenance declares origin;
rep statuses and real archives establish which measurements succeeded.

Full telemetry now records timestamped memory, clocks, power, temperature and
utilization. Unsupported fields are null. GSM8K scheduling now shares successful
model/precision/protocol evidence, while combined configurations are measured
separately; rows and recommendations retain the source launch/quality ID. The
reference sample files must remain available for paired comparisons and resume.
Repeated baseline launches still provide independent performance observations,
not additional independent GSM8K samples. Agreement checks continue per launch.
The completed Qwen campaign exercised these paths on the pinned live stack;
[fixture coverage](FIXTURE_COVERAGE.md) states which unobserved cases remain synthetic.

## Small quality pilot before the campaign

After measured calibration and hardware probes, run
`python scripts/live_pilot.py --config data/measured.yaml --out data/pilot` in the
isolated live environment. This starts and tears down one owned baseline server,
checks returned token IDs on two prompts, and parses the first 16 GSM8K problems.
Inspect `pilot.json` and the harness log before committing to the long campaign.
Pilot timings include harness setup and are preliminary budget evidence; the pilot
does not replace the campaign's quality evaluation or baseline replication.

The detached launcher also accepts `--quality-limit N` when a measured budget
requires a fixed first-N GSM8K subset. Omit it for all 1,319 problems. Record the
budget reason before evaluation; resume uses the runner's persisted protocol.
