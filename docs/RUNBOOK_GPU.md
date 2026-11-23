# M9 owner GPU campaign

M0–M8 use synthetic offline evidence. Live GPU execution is **not run (needs GPU)**.
The scripts below are prepared for the owner; no rental or live deployment is automated.

## Rental and setup

Use the project's specified **one NVIDIA A100 80 GB SXM4**, with at least **150 GB disk**,
SSH access, and a pinned CUDA-compatible image that does not auto-launch vLLM. Reserve
an **8–14 GPU-hour campaign window**, plus installation/download/calibration time; the
runner's default 14-hour wall-clock cap starts at experiment creation, not at rental.
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
