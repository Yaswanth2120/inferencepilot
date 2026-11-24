"""SQLite checkpoints and raw artifacts; schema follows AGENTS section 11."""

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA = "CREATE TABLE IF NOT EXISTS schema_meta (\n    key   TEXT PRIMARY KEY,\n    value TEXT NOT NULL\n);\n\nCREATE TABLE IF NOT EXISTS env_snapshots (\n    id         TEXT PRIMARY KEY,\n    created_at REAL NOT NULL,\n    data       TEXT NOT NULL\n);\n\nCREATE TABLE IF NOT EXISTS experiments (\n    id                TEXT PRIMARY KEY,\n    name              TEXT NOT NULL,\n    created_at        REAL NOT NULL,\n    plan              TEXT NOT NULL,\n    status            TEXT NOT NULL CHECK (status IN ('planned','running','completed','aborted')),\n    abort_reason      TEXT,\n    env_id            TEXT REFERENCES env_snapshots(id),\n    budget_gpu_hours  REAL,\n    seed              INTEGER NOT NULL\n);\n\nCREATE TABLE IF NOT EXISTS configs (\n    id            TEXT PRIMARY KEY,\n    experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,\n    label         TEXT NOT NULL,\n    role          TEXT NOT NULL CHECK (role IN ('baseline','candidate','seeded_regression','combined')),\n    spec          TEXT NOT NULL,\n    spec_hash     TEXT NOT NULL,\n    UNIQUE (experiment_id, label)\n);\n\nCREATE TABLE IF NOT EXISTS launches (\n    id               TEXT PRIMARY KEY,\n    config_id        TEXT NOT NULL REFERENCES configs(id) ON DELETE CASCADE,\n    ordinal          INTEGER NOT NULL,\n    started_at       REAL NOT NULL,\n    ready_at         REAL,\n    stopped_at       REAL,\n    status           TEXT NOT NULL CHECK (status IN ('ok','server_failed','unsupported_on_hardware','aborted')),\n    cmd              TEXT NOT NULL,\n    resolved_args    TEXT NOT NULL DEFAULT '{}',\n    startup_seconds  REAL,\n    log_path         TEXT,\n    error            TEXT,\n    UNIQUE (config_id, ordinal)\n);\n\nCREATE TABLE IF NOT EXISTS points (\n    id            TEXT PRIMARY KEY,\n    launch_id     TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,\n    workload      TEXT NOT NULL,\n    mode          TEXT NOT NULL CHECK (mode IN ('closed','open')),\n    concurrency   INTEGER,\n    request_rate  REAL,\n    num_prompts   INTEGER NOT NULL,\n    params        TEXT NOT NULL DEFAULT '{}'\n);\n\nCREATE TABLE IF NOT EXISTS reps (\n    id            TEXT PRIMARY KEY,\n    point_id      TEXT NOT NULL REFERENCES points(id) ON DELETE CASCADE,\n    rep           INTEGER NOT NULL,\n    seed          INTEGER NOT NULL,\n    started_at    REAL NOT NULL,\n    duration_s    REAL,\n    status        TEXT NOT NULL CHECK (status IN ('ok','failed','partial')),\n    completed     INTEGER,\n    failed        INTEGER,\n    raw_path      TEXT,\n    summary       TEXT NOT NULL DEFAULT '{}',\n    tool_summary  TEXT NOT NULL DEFAULT '{}',\n    gpu_before    TEXT,\n    gpu_after     TEXT,\n    UNIQUE (point_id, rep)\n);\nCREATE INDEX IF NOT EXISTS idx_reps_point ON reps (point_id);\n\nCREATE TABLE IF NOT EXISTS quality_results (\n    id           TEXT PRIMARY KEY,\n    launch_id    TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,\n    task         TEXT NOT NULL,\n    n            INTEGER NOT NULL,\n    metrics      TEXT NOT NULL,\n    samples_path TEXT,\n    created_at   REAL NOT NULL\n);\n\nCREATE TABLE IF NOT EXISTS agreement_results (\n    id                    TEXT PRIMARY KEY,\n    launch_id             TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,\n    reference_launch_id   TEXT NOT NULL REFERENCES launches(id),\n    n                     INTEGER NOT NULL,\n    exact_match_rate      REAL NOT NULL,\n    mean_first_divergence REAL,\n    samples_path          TEXT\n);\n\nCREATE TABLE IF NOT EXISTS regression_results (\n    id                  TEXT PRIMARY KEY,\n    experiment_id       TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,\n    baseline_config_id  TEXT NOT NULL REFERENCES configs(id),\n    candidate_config_id TEXT NOT NULL REFERENCES configs(id),\n    workload            TEXT NOT NULL,\n    point_key           TEXT NOT NULL,\n    metric              TEXT NOT NULL,\n    direction           TEXT NOT NULL CHECK (direction IN ('lower_better','higher_better')),\n    effect_pct          REAL,\n    ci_low              REAL,\n    ci_high             REAL,\n    p_value             REAL,\n    p_adjusted          REAL,\n    mde_pct             REAL,\n    n_baseline          INTEGER NOT NULL,\n    n_candidate         INTEGER NOT NULL,\n    verdict             TEXT NOT NULL CHECK (verdict IN ('regression','improvement','no_change','inconclusive'))\n);\nCREATE INDEX IF NOT EXISTS idx_regress_cand ON regression_results (candidate_config_id, verdict);\n\nCREATE TABLE IF NOT EXISTS recommendations (\n    id               TEXT PRIMARY KEY,\n    experiment_id    TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,\n    constraints      TEXT NOT NULL,\n    ranking          TEXT NOT NULL,\n    chosen_config_id TEXT REFERENCES configs(id),\n    created_at       REAL NOT NULL\n);\n"
TABLES = {
    "env_snapshots",
    "experiments",
    "configs",
    "launches",
    "points",
    "reps",
    "quality_results",
    "agreement_results",
    "regression_results",
    "recommendations",
}


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        version = self.meta("version")
        if version not in (None, "1"):
            self.connection.close()
            raise ValueError(f"schema version mismatch: expected 1, found {version}")
        self.connection.executescript(SCHEMA)
        self.set_meta("version", "1")
        self.raw_dir = self.path.parent / "raw"
        self.raw_dir.mkdir(exist_ok=True)

    def close(self):
        self.connection.close()

    def meta(self, key):
        row = self.connection.execute(
            "SELECT value FROM schema_meta WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key, value):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO schema_meta VALUES (?,?)", (key, value))

    def rows(self, table, **where):
        if table not in TABLES:
            raise ValueError("unknown table")
        columns = {r[1] for r in self.connection.execute(f"PRAGMA table_info({table})")}
        if not where.keys() <= columns:
            raise ValueError("unknown column")
        clause = " AND ".join(f"{key}=?" for key in where) or "1"
        return [
            dict(r)
            for r in self.connection.execute(
                f"SELECT * FROM {table} WHERE {clause}", tuple(where.values())
            )
        ]

    def insert(self, table, **values):
        self.rows(table, **{k: None for k in values})
        values.setdefault("id", uuid.uuid4().hex)
        keys = ",".join(values)
        with self.connection:
            self.connection.execute(
                f"INSERT INTO {table} ({keys}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
        return values["id"]

    def update(self, table, identity, **values):
        self.rows(table, **{k: None for k in values})
        with self.connection:
            self.connection.execute(
                f"UPDATE {table} SET {','.join(k + '=?' for k in values)} WHERE id=?",
                (*values.values(), identity),
            )

    def checkpoint_rep(self, key, **values):
        identity = uuid.uuid4().hex
        values = {"id": identity, **values}
        self.rows("reps", **{k: None for k in values})
        with self.connection:
            self.connection.execute(
                f"INSERT INTO reps ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
            self.connection.execute("INSERT INTO schema_meta VALUES (?,?)", (key, identity))
        return identity

    def artifact(self, name):
        if Path(name).name != name:
            raise ValueError("artifact must be a filename")
        return self.raw_dir / name

    def create(self, plan, snapshot, budget):
        env_id = self.insert("env_snapshots", created_at=time.time(), data=encode(snapshot))
        identity = self.insert(
            "experiments",
            name=plan.experiment.name,
            created_at=time.time(),
            plan=plan.model_dump_json(),
            status="planned",
            env_id=env_id,
            budget_gpu_hours=budget,
            seed=plan.experiment.seed,
        )
        for config in plan.configs:
            spec = encode(config.spec.model_dump() if config.spec else None)
            self.insert(
                "configs",
                experiment_id=identity,
                label=config.label,
                role=config.role,
                spec=spec,
                spec_hash=hashlib.sha256(spec.encode()).hexdigest(),
            )
        return identity

    def records(self, experiment):
        result = {"experiment": self.rows("experiments", id=experiment)[0]}
        configs = self.rows("configs", experiment_id=experiment)
        launches = [r for c in configs for r in self.rows("launches", config_id=c["id"])]
        points = [r for launch in launches for r in self.rows("points", launch_id=launch["id"])]
        result.update(
            configs=configs,
            launches=launches,
            points=points,
            reps=[r for p in points for r in self.rows("reps", point_id=p["id"])],
            quality=[
                r
                for launch in launches
                for r in self.rows("quality_results", launch_id=launch["id"])
            ],
            agreement=[
                r
                for launch in launches
                for r in self.rows("agreement_results", launch_id=launch["id"])
            ],
        )
        return result

    def replace_regressions(self, experiment, rows):
        with self.connection:
            self.connection.execute(
                "DELETE FROM regression_results WHERE experiment_id=?", (experiment,)
            )
            for row in rows:
                values = {"id": uuid.uuid4().hex, "experiment_id": experiment, **row}
                self.connection.execute(
                    f"INSERT INTO regression_results ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                    tuple(values.values()),
                )

    def checkpoint_quality(self, key, **values):
        """Commit measured quality and its reusable source identity atomically."""
        values = {"id": uuid.uuid4().hex, **values}
        self.rows("quality_results", **{k: None for k in values})
        with self.connection:
            self.connection.execute(
                f"INSERT INTO quality_results ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO schema_meta VALUES (?,?)", (key, values["id"])
            )
        return values["id"]


def latest_experiment_id(path):
    """Read a committed experiment identity without creating a database or migrating it."""
    path = Path(path).resolve()
    if not path.exists():
        return None
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
        row = connection.execute(
            "SELECT id FROM experiments ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        if connection is not None:
            connection.close()
