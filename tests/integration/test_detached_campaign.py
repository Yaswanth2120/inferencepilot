import json
import os
import subprocess
import sys
import time
from pathlib import Path

from inferencepilot.config import ProbeEvidence
from inferencepilot.fakes.selftest import mini_plan
from inferencepilot.planner import make_plan

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/detached_campaign.py"


def fixture_plan(tmp_path):
    experiment = mini_plan().experiment
    experiment.calibration.source = "measured"
    experiment.probes["bf16"] = ProbeEvidence(status="supported", evidence="SYNTHETIC test fixture")
    path = tmp_path / "plan.json"
    path.write_text(make_plan(experiment).model_dump_json())
    return path


def fake_cli(tmp_path):
    path = tmp_path / "fake-cli"
    path.write_text(
        f"#!{sys.executable}\n"
        + """import json
import os
import sqlite3
import sys
import time
from pathlib import Path
args = sys.argv[1:]
if args[0] == 'run':
    Path(sys.argv[0]).with_suffix('.run.json').write_text(json.dumps(args))
    db = sqlite3.connect(args[args.index('--db') + 1])
    db.execute('CREATE TABLE experiments (id TEXT, created_at REAL, status TEXT)')
    db.execute("INSERT INTO experiments VALUES ('synthetic-id', 1, 'running')")
    db.commit()
    time.sleep(float(os.environ.get('FAKE_DETACHED_DELAY', '1')))
    db.execute("UPDATE experiments SET status='completed'")
    db.commit()
    db.close()
if args[0] == 'report':
    out = Path(args[args.index('--out') + 1])
    out.mkdir(parents=True)
    (out / 'report.json').write_text(json.dumps({'synthetic': True}))
if args[0] == 'regress':
    raise SystemExit(1)
"""
    )
    path.chmod(0o755)
    return path


def wait_terminal(directory):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            state = json.loads((directory / "status.json").read_text())
            if state["phase"] in ("completed", "failed", "aborted") and "finished_at" in state:
                return state
        except FileNotFoundError:
            pass
        time.sleep(0.05)
    raise AssertionError("detached worker did not reach terminal status")


def launch(tmp_path, hours="1", extra=(), delay="1"):
    directory = tmp_path / "job"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "start",
            "--plan",
            str(fixture_plan(tmp_path)),
            "--db",
            str(tmp_path / "data" / "campaign.db"),
            "--state-dir",
            str(directory),
            "--max-hours",
            hours,
            "--cli",
            str(fake_cli(tmp_path)),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
        env={**os.environ, "FAKE_DETACHED_DELAY": delay},
    )
    return directory, json.loads(result.stdout)


def test_survives_launcher_exit_and_reports(tmp_path):
    directory, launched = launch(tmp_path)
    # The launcher has exited, yet its child continues independently and writes final artifacts.
    assert launched["worker_pid"] != os.getpid()
    state = wait_terminal(directory)
    assert state["phase"] == "completed", (directory / "worker.log").read_text()
    assert state["experiment"] == "synthetic-id"
    assert state["stages"]["regress"] == 1  # A finding must not suppress the report stage.
    assert state["stages"]["report"] == 0
    assert json.loads((directory / "reports/report.json").read_text())["synthetic"]
    status = subprocess.run(
        [sys.executable, str(SCRIPT), "status", "--state-dir", str(directory)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(status.stdout)["phase"] == "completed"


def test_independent_runtime_guard(tmp_path):
    directory, _ = launch(tmp_path, hours=".0005", delay="30")
    state = wait_terminal(directory)
    assert state["phase"] == "aborted"
    assert "runtime exhausted" in state["error"]
    assert "report" not in state["stages"]
    assert "does not stop or destroy" in state["billing"]


def test_detached_quality_subset_is_passed_to_runner(tmp_path):
    directory, _ = launch(tmp_path, extra=("--quality-limit", "200"))
    state = wait_terminal(directory)
    assert state["phase"] == "completed"
    arguments = json.loads((tmp_path / "fake-cli.run.json").read_text())
    assert arguments[arguments.index("--quality-limit") + 1] == "200"
    assert json.loads((directory / "job.json").read_text())["quality_limit"] == 200


def test_refuses_synthetic_and_existing_state(tmp_path):
    path = tmp_path / "synthetic.json"
    path.write_text(mini_plan().model_dump_json())
    command = [
        sys.executable,
        str(SCRIPT),
        "start",
        "--plan",
        str(path),
        "--db",
        str(tmp_path / "db"),
        "--state-dir",
        str(tmp_path / "job"),
        "--max-hours",
        "5",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "measured calibration required" in result.stderr
    assert not (tmp_path / "job").exists()
    directory, _ = launch(tmp_path)
    wait_terminal(directory)
    path.write_text(fixture_plan(tmp_path).read_text())
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2


def test_final_backup_survives_worker_exit(tmp_path):
    backup = tmp_path / "off-machine-fixture"
    directory, _ = launch(tmp_path, extra=("--backup-to", str(backup), "--backup-seconds", "1"))
    state = wait_terminal(directory)
    assert state["phase"] == "completed"
    assert state["backups"] and all(item.get("returncode") == 0 for item in state["backups"])
    import sqlite3

    connection = sqlite3.connect(backup / "experiment.db")
    try:
        assert connection.execute("SELECT status FROM experiments").fetchone()[0] == "completed"
    finally:
        connection.close()
