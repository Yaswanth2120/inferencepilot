#!/usr/bin/env bash
# Owner executes on the GPU host. Preview is the default.
set -euo pipefail
if [[ ${1:-} == --help || $# -lt 2 || $# -gt 3 ]]; then
  echo 'Usage: scripts/run_campaign.sh PLAN.json DB [--execute]'
  echo 'Default: preview only. --execute requires measured calibration and completed probes.'
  [[ ${1:-} == --help ]] && exit 0
  exit 2
fi
plan=$1
campaign_db=$2
if [[ $# == 2 ]]; then
  exec inferencepilot run --plan "$plan" --db "$campaign_db" --dry-run
fi
[[ $3 == --execute ]] || { echo 'Expected --execute'; exit 2; }
python3 - "$plan" <<'PY'
import sys
from pathlib import Path
from inferencepilot.config import ExperimentPlan
plan = ExperimentPlan.model_validate_json(Path(sys.argv[1]).read_text())
if plan.experiment.calibration.source != 'measured':
    raise SystemExit('Live campaign requires measured calibration; run scripts/calibrate.py first.')
if plan.budget_exceeded:
    raise SystemExit('Estimated schedule exceeds the budget; revise the design before execution.')
for config in plan.configs:
    if config.spec is not None and config.probe_status == 'pending':
        raise SystemExit(f'Unresolved load probe: {config.label}')
PY
inferencepilot doctor
exec inferencepilot run --plan "$plan" --db "$campaign_db" --constraints configs/constraints.yaml
