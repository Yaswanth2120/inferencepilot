#!/usr/bin/env python3
"""Detached campaign supervision without an assistant, tmux, or cloud credentials."""

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from inferencepilot.config import ExperimentPlan
from inferencepilot.store import latest_experiment_id

ROOT = Path(__file__).resolve().parents[1]


def save_state(directory, state):
    """Atomically replace progress so readers never see a half-written JSON document."""
    state["updated_at"] = time.time()
    temporary = directory / "status.tmp"
    temporary.write_text(json.dumps(state, indent=2, allow_nan=False) + "\n")
    temporary.replace(directory / "status.json")


def experiment_id(database):
    """Read the latest experiment once the runner has committed its initial checkpoint."""
    return latest_experiment_id(database)


def start(args):
    """Validate the live prerequisites and launch a session-independent worker."""
    plan = ExperimentPlan.model_validate_json(Path(args.plan).read_text())
    if plan.experiment.calibration.source != "measured":
        raise ValueError(
            "measured calibration required; synthetic plans cannot launch live automation"
        )
    if plan.budget_exceeded:
        raise ValueError("plan estimate exceeds its configured budget")
    if any(c.spec is not None and c.probe_status == "pending" for c in plan.configs):
        raise ValueError("complete load probes before launching automation")
    if args.max_hours <= 0 or not args.max_hours < float("inf"):
        raise ValueError("--max-hours must be finite and positive")
    if args.backup_seconds < 1:
        raise ValueError("--backup-seconds must be positive")
    database = Path(args.db).resolve()
    directory = Path(args.state_dir).resolve()
    if database.exists() and not args.resume:
        raise ValueError("database exists; specify --resume EXPERIMENT or use a fresh database")
    if args.resume and experiment_id(database) != args.resume:
        raise ValueError("--resume must identify the latest experiment in the database")
    if args.backup_to and ":" not in args.backup_to:
        backup = Path(args.backup_to).resolve()
        if backup.is_relative_to(database.parent):
            raise ValueError("backup destination must be outside the source data directory")
        args.backup_to = str(backup)
    # A fresh state directory prevents overwriting an earlier job or racing another launcher.
    directory.mkdir(parents=True, exist_ok=False)
    database.parent.mkdir(parents=True, exist_ok=True)
    lock = (directory / "job.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    payload = vars(args).copy()
    for field in ("plan", "db", "constraints", "state_dir"):
        payload[field] = str(Path(payload[field]).resolve())
    (directory / "job.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (directory / "worker.log").open("a") as log:
        worker = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "_worker",
                str(directory),
                str(lock.fileno()),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            pass_fds=(lock.fileno(),),
            cwd=ROOT,
        )
    lock.close()
    print(
        json.dumps(
            {
                "worker_pid": worker.pid,
                "state_dir": str(directory),
                "status": str(directory / "status.json"),
                "log": str(directory / "worker.log"),
            }
        )
    )
    return 0


class Supervisor:
    def __init__(self, directory):
        self.directory = directory
        self.job = json.loads((directory / "job.json").read_text())
        self.database = Path(self.job["db"])
        self.started = time.time()
        self.deadline = self.started + self.job["max_hours"] * 3600
        self.next_backup = self.started + self.job["backup_seconds"]
        self.state = dict(
            phase="starting",
            pid=os.getpid(),
            started_at=self.started,
            deadline=self.deadline,
            experiment=self.job["resume"],
            stages={},
            backups=[],
            billing="This job does not stop or destroy the rental instance.",
        )
        self.child = None
        self.interrupted = False

    def interrupt(self, signum, frame):
        self.interrupted = True

    def checkpoint(self):
        self.state["experiment"] = self.state["experiment"] or experiment_id(self.database)
        save_state(self.directory, self.state)

    def stop_child(self):
        """Signal only a child group started here, giving the runner time for server cleanup."""
        if self.child is not None and self.child.poll() is None:
            try:
                os.killpg(self.child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.child.wait(timeout=240)
            except subprocess.TimeoutExpired:
                os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait()
                self.state["cleanup_warning"] = (
                    "Runner cleanup timed out; inspect surviving servers before resume."
                )

    def backup(self):
        """Invoke the existing consistent SQLite backup and record failures without hiding them."""
        if not self.job["backup_to"] or not self.database.exists():
            return
        try:
            process = subprocess.Popen(
                [
                    "bash",
                    str(ROOT / "scripts/sync_results.sh"),
                    str(self.database),
                    str(self.database.parent),
                    self.job["backup_to"],
                ],
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, "RSYNC_RSH": "ssh -o BatchMode=yes -o ConnectTimeout=15"},
            )
            try:
                timeout = (
                    120
                    if self.state["phase"] in ("completed", "failed", "aborted")
                    else max(1, min(120, self.deadline - time.time()))
                )
                record = dict(at=time.time(), returncode=process.wait(timeout=timeout))
            finally:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
        except (OSError, subprocess.TimeoutExpired) as error:
            record = dict(at=time.time(), error=str(error))
        self.state["backups"].append(record)
        self.next_backup = time.time() + self.job["backup_seconds"]
        self.checkpoint()

    def stage(self, name, arguments, allowed=(0,)):
        """Run a CLI stage, tracking its exit status and enforcing the independent deadline."""
        self.state["phase"] = name
        self.checkpoint()
        if self.interrupted or time.time() >= self.deadline:
            raise TimeoutError("configured automation runtime exhausted or interrupted")
        print(f"Starting {name}", flush=True)
        self.child = subprocess.Popen(
            [self.job["cli"], *arguments], stdin=subprocess.DEVNULL, start_new_session=True
        )
        try:
            while self.child.poll() is None:
                if self.interrupted or time.time() >= self.deadline:
                    raise TimeoutError("configured automation runtime exhausted or interrupted")
                if time.time() >= self.next_backup:
                    self.backup()
                self.checkpoint()
                time.sleep(0.5)
            code = self.child.returncode
            self.state["stages"][name] = code
            self.checkpoint()
            if code not in allowed:
                raise RuntimeError(f"{name} exited {code}; inspect worker.log and the database")
        finally:
            self.stop_child()

    def run(self):
        """Execute the campaign and its analyses, then preserve a terminal status and final backup."""
        previous = {
            sig: signal.signal(sig, self.interrupt) for sig in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            self.stage("doctor", ["doctor"])
            if self.job["resume"]:
                arguments = [
                    "resume",
                    "--db",
                    str(self.database),
                    "--experiment",
                    self.job["resume"],
                ]
            else:
                arguments = [
                    "run",
                    "--evidence",
                    "live",
                    "--plan",
                    self.job["plan"],
                    "--db",
                    str(self.database),
                    "--constraints",
                    self.job["constraints"],
                    "--max-gpu-hours",
                    str(self.job["max_hours"]),
                ]
                if self.job.get("quality_limit") is not None:
                    arguments.extend(["--quality-limit", str(self.job["quality_limit"])])
            self.stage("campaign", arguments)
            identity = self.state["experiment"]
            if identity is None:
                raise RuntimeError("runner returned without creating an experiment")
            common = ["--db", str(self.database), "--experiment", identity]
            self.stage("analyze", ["analyze", *common])
            self.stage("validate", ["validate", *common])
            self.stage("regress", ["regress", *common, "--baseline", "baseline"], allowed=(0, 1))
            self.stage(
                "recommend", ["recommend", *common, "--constraints", self.job["constraints"]]
            )
            self.stage("report", ["report", *common, "--out", str(self.directory / "reports")])
            self.state["phase"] = "completed"
        except TimeoutError as error:
            self.state.update(phase="aborted", error=str(error))
        except Exception as error:
            self.state.update(phase="failed", error=str(error))
        finally:
            self.stop_child()
            self.checkpoint()
            self.backup()
            self.state["finished_at"] = time.time()
            self.checkpoint()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        return 0 if self.state["phase"] == "completed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    launch = commands.add_parser("start")
    for name in ("plan", "db", "state-dir"):
        launch.add_argument("--" + name, required=True)
    launch.add_argument("--constraints", default=str(ROOT / "configs/constraints.yaml"))
    launch.add_argument("--max-hours", type=float, required=True)
    launch.add_argument("--resume")
    launch.add_argument("--quality-limit", type=int, choices=range(1, 1320))
    launch.add_argument("--backup-to")
    launch.add_argument("--backup-seconds", type=int, default=3600)
    launch.add_argument("--cli", default=str(Path(sys.executable).parent / "inferencepilot"))
    status = commands.add_parser("status")
    status.add_argument("--state-dir", required=True)
    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("directory")
    worker.add_argument("lock_fd", type=int)
    args = parser.parse_args()
    try:
        if args.command == "start":
            return start(args)
        if args.command == "status":
            print((Path(args.state_dir) / "status.json").read_text())
            return 0
        # Keep the inherited lock alive for the entire worker lifetime.
        with os.fdopen(args.lock_fd, "a"):
            return Supervisor(Path(args.directory)).run()
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
