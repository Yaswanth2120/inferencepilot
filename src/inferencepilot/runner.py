"""Checkpointed orchestration. All statistics belong to metrics/analysis/quality."""

import asyncio
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field

from inferencepilot import analysis, env, quality
from inferencepilot.config import ConfigSpec, ExperimentPlan, LoadSpec
from inferencepilot.loadgen import build_command, parse_result
from inferencepilot.metrics import summarize
from inferencepilot.server import ServerManager, ServerTimeouts
from inferencepilot.store import encode


@dataclass
class Options:
    binary: str = "vllm"
    quality_binary: str = "lm_eval"
    quality_limit: int | None = None
    agreement_count: int = 200
    agreement_tokens: int = 64
    timeouts: ServerTimeouts = field(default_factory=ServerTimeouts)


def execute(argv, log, timeout):
    """Bound a child command and reap its owned process group on interruption."""
    with open(log, "w") as output:
        process = subprocess.Popen(
            argv, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            code = process.wait(timeout=timeout)
            if code:
                raise ValueError(f"command exited {code}; see {log}")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


class Runner:
    def __init__(self, store, options=None):
        self.store = store
        self.options = options or Options()
        self.deadline = None

    def remaining(self):
        seconds = self.deadline - time.time()
        if seconds <= 0:
            raise TimeoutError("wall-clock GPU-hour budget exhausted")
        return seconds

    def run(self, plan=None, experiment=None, budget=None):
        with open(str(self.store.path) + ".runner.lock", "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("another runner owns this database") from error
            if experiment is None:
                cap = plan.experiment.max_gpu_hours if budget is None else budget
                if not math.isfinite(cap) or cap <= 0:
                    raise ValueError("budget must be finite and positive")
                experiment = self.store.create(plan, env.snapshot(), cap)
                self.store.set_meta(
                    "options:" + experiment,
                    encode({k: v for k, v in asdict(self.options).items() if k != "timeouts"}),
                )
            row = self.store.rows("experiments", id=experiment)[0]
            plan = ExperimentPlan.model_validate_json(row["plan"])
            self.deadline = row["created_at"] + row["budget_gpu_hours"] * 3600
            self.store.update("experiments", experiment, status="running", abort_reason=None)
            try:
                for slot, launch in enumerate(plan.launches):
                    self.remaining()
                    self.launch(experiment, plan, launch, slot)
                self.store.update("experiments", experiment, status="completed")
            except (KeyboardInterrupt, TimeoutError) as error:
                self.store.update(
                    "experiments",
                    experiment,
                    status="aborted",
                    abort_reason=str(error) or "interrupted",
                )
            except BaseException as error:
                self.store.update(
                    "experiments", experiment, status="aborted", abort_reason=str(error)
                )
                raise
            return experiment

    def launch(self, experiment, plan, scheduled, slot):
        config = self.store.rows("configs", experiment_id=experiment, label=scheduled.config_label)[
            0
        ]
        checkpoint = f"slot:{experiment}:{slot}"
        if self.store.meta(checkpoint) == "done":
            return
        if json.loads(config["spec"]) is None:
            spec = analysis.combined_spec(self.store.records(experiment), plan.experiment.baseline)
            serialized = encode(spec.model_dump())
            self.store.update(
                "configs",
                config["id"],
                spec=serialized,
                spec_hash=hashlib.sha256(serialized.encode()).hexdigest(),
            )
        else:
            spec = ConfigSpec.model_validate_json(config["spec"])
        manager = ServerManager(
            binary=self.options.binary,
            log_dir=self.store.path.parent / "logs",
            timeouts=self.options.timeouts,
        )
        ordinal = len(self.store.rows("launches", config_id=config["id"])) + 1
        launch_id = self.store.insert(
            "launches",
            config_id=config["id"],
            ordinal=ordinal,
            started_at=time.time(),
            status="aborted",
            cmd="[]",
            resolved_args=encode({"schedule_slot": slot}),
        )
        try:
            self.remaining()
            result = manager.start(spec, launch_id=launch_id)
            self.store.update(
                "launches",
                launch_id,
                cmd=encode(result.cmd),
                ready_at=result.ready_at,
                startup_seconds=result.startup_seconds,
                status=result.status,
                resolved_args=encode({**result.resolved_args, "schedule_slot": slot}),
                log_path=str(result.log_path),
                error=result.error,
            )
            if result.status != "ok":
                self.store.set_meta(checkpoint, "done")
                return
            workloads = {w.name: w for w in plan.experiment.workloads}
            for point in scheduled.points:
                self.point(
                    experiment,
                    launch_id,
                    slot,
                    spec,
                    workloads[point.workload],
                    LoadSpec(concurrency=point.concurrency),
                    point.rep_seeds,
                )
            capacity_key = "capacity:" + experiment
            if config["role"] == "baseline" and self.store.meta(capacity_key) is None:
                measured = analysis.capacity(self.store.records(experiment), config["id"])
                if measured:
                    self.store.set_meta(capacity_key, encode(measured))
            measured = self.store.meta(capacity_key)
            if measured and "chat" in workloads:
                measured = json.loads(measured)
                seeds = next(p.rep_seeds for p in scheduled.points if p.workload == "chat")
                for fraction in measured["fractions"]:
                    self.point(
                        experiment,
                        launch_id,
                        slot,
                        spec,
                        workloads["chat"],
                        LoadSpec(
                            mode="open", request_rate=measured["requests_per_second"] * fraction
                        ),
                        seeds,
                    )
            self.check_quality(experiment, launch_id, spec, config)
            self.remaining()
            self.store.set_meta(checkpoint, "done")
        except (KeyboardInterrupt, TimeoutError):
            self.store.update(
                "launches", launch_id, status="aborted", error="interrupted or budget exhausted"
            )
            raise
        finally:
            manager.stop()
            self.store.update("launches", launch_id, stopped_at=time.time())

    def point(self, experiment, launch_id, slot, spec, workload, load, seeds):
        self.remaining()
        params = load.model_dump()
        identity = self.store.insert(
            "points",
            launch_id=launch_id,
            workload=workload.name,
            mode=load.mode,
            concurrency=load.concurrency,
            request_rate=load.request_rate,
            num_prompts=workload.num_prompts,
            params=encode({"slot": slot, "seeds": seeds}),
        )
        for index, seed in enumerate(seeds):
            key = "rep:" + encode([experiment, slot, workload.name, params, index])
            if self.store.meta(key):
                continue
            timeout = self.remaining()
            raw = self.store.artifact(identity + f"-{index}.json")
            started = time.time()
            before = env.gpu_memory_used()
            try:
                command = build_command(spec, workload, load, seed, raw, binary=self.options.binary)
                execute(command, raw.with_suffix(".log"), timeout)
                parsed = parse_result(json.loads(raw.read_text()))
                summary = summarize(parsed, workload.output_tokens)
                values = dict(
                    status=summary.status,
                    completed=summary.completed,
                    failed=summary.failed,
                    duration_s=parsed.duration_s,
                    summary=encode(asdict(summary)),
                    tool_summary=encode(parsed.tool_summary),
                )
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                values = dict(status="failed", summary=encode({"error": str(error)}))
            self.store.checkpoint_rep(
                key,
                point_id=identity,
                rep=index,
                seed=seed,
                started_at=started,
                raw_path=str(raw),
                gpu_before=encode(before),
                gpu_after=encode(env.gpu_memory_used()),
                **values,
            )

    def check_quality(self, experiment, launch_id, spec, config):
        self.remaining()
        directory = self.store.artifact(launch_id + "-quality")
        directory.mkdir(exist_ok=True)
        try:
            execute(
                quality.quality_command(
                    spec.model,
                    spec.port,
                    directory,
                    limit=self.options.quality_limit,
                    seed=spec.seed,
                    binary=self.options.quality_binary,
                ),
                directory / "harness.log",
                self.remaining(),
            )
            paths = list(directory.rglob("*samples*gsm8k*.jsonl"))
            if len(paths) != 1:
                raise ValueError("expected exactly one gsm8k sample log")
            samples = quality.read_samples(paths[0], self.options.quality_limit or 1319)
            metrics = {"status": "ok", "filters": quality.quality_summary(samples)}
            baseline_key = "quality_baseline:" + experiment
            baseline = self.store.meta(baseline_key)
            if baseline:
                metrics["paired"] = quality.paired_quality(quality.read_samples(baseline), samples)
            elif config["role"] == "baseline":
                self.store.set_meta(baseline_key, str(paths[0]))
            self.store.insert(
                "quality_results",
                launch_id=launch_id,
                task="gsm8k",
                n=self.options.quality_limit or 1319,
                metrics=encode(metrics),
                samples_path=str(paths[0]),
                created_at=time.time(),
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            self.store.insert(
                "quality_results",
                launch_id=launch_id,
                task="gsm8k",
                n=0,
                metrics=encode({"status": "failed", "error": str(error)}),
                created_at=time.time(),
            )
        reference_key = "agreement_baseline:" + experiment
        reference = self.store.meta(reference_key)
        try:
            previous = json.loads(reference) if reference else None
            outputs, compared = asyncio.run(
                quality.agreement_check(
                    f"http://127.0.0.1:{spec.port}",
                    spec.model,
                    reference_outputs=previous["outputs"] if previous else None,
                    prompts=quality.fixed_prompts()[: self.options.agreement_count],
                    max_tokens=self.options.agreement_tokens,
                )
            )
            path = self.store.artifact(launch_id + "-agreement.json")
            path.write_text(encode(outputs))
            if previous:
                self.store.insert(
                    "agreement_results",
                    launch_id=launch_id,
                    reference_launch_id=previous["launch_id"],
                    n=compared["n"],
                    exact_match_rate=compared["exact_match_rate"],
                    mean_first_divergence=compared["mean_first_divergence"],
                    samples_path=str(path),
                )
            elif config["role"] == "baseline":
                self.store.set_meta(
                    reference_key, encode({"outputs": outputs, "launch_id": launch_id})
                )
        except Exception as error:
            # HTTP and schema errors must remain visible without fabricating agreement.
            self.store.insert(
                "quality_results",
                launch_id=launch_id,
                task="agreement_error",
                n=0,
                metrics=encode({"status": "failed", "error": str(error)}),
                created_at=time.time(),
            )
