#!/usr/bin/env bash
# Run on the GPU host; DEST can be a mounted directory or owner-configured SSH destination.
set -euo pipefail
if [[ ${1:-} == --help || $# != 3 ]]; then
  echo 'Usage: scripts/sync_results.sh DB DATA_DIRECTORY DESTINATION'
  echo 'Copies a consistent SQLite backup plus immutable raw artifacts; never deletes destination files.'
  [[ ${1:-} == --help ]] && exit 0
  exit 2
fi
campaign_db=$1
campaign_data=$2
campaign_destination=$3
[[ -f "$campaign_db" && -d "$campaign_data" ]] || { echo 'Database/data directory missing'; exit 2; }
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
python3 - "$campaign_db" "$stage/experiment.db" <<'PY'
import sqlite3
import sys
from pathlib import Path
source = sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True)
destination = sqlite3.connect(sys.argv[2])
try:
    source.backup(destination)
    if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('Backup integrity check failed')
finally:
    destination.close()
    source.close()
PY
rsync -a -- "$stage/" "$campaign_destination/"
rsync -a --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' -- "$campaign_data/" "$campaign_destination/data/"
echo 'Backup copied. Verify experiment.db and data/raw on the destination before destroying the instance.'
