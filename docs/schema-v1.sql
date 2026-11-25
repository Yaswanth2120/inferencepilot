CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS env_snapshots (
    id         TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    data       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    created_at        REAL NOT NULL,
    plan              TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('planned','running','completed','aborted')),
    abort_reason      TEXT,
    env_id            TEXT REFERENCES env_snapshots(id),
    budget_gpu_hours  REAL,
    seed              INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS configs (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('baseline','candidate','seeded_regression','combined')),
    spec          TEXT NOT NULL,
    spec_hash     TEXT NOT NULL,
    UNIQUE (experiment_id, label)
);

CREATE TABLE IF NOT EXISTS launches (
    id               TEXT PRIMARY KEY,
    config_id        TEXT NOT NULL REFERENCES configs(id) ON DELETE CASCADE,
    ordinal          INTEGER NOT NULL,
    started_at       REAL NOT NULL,
    ready_at         REAL,
    stopped_at       REAL,
    status           TEXT NOT NULL CHECK (status IN ('ok','server_failed','unsupported_on_hardware','aborted')),
    cmd              TEXT NOT NULL,
    resolved_args    TEXT NOT NULL DEFAULT '{}',
    startup_seconds  REAL,
    log_path         TEXT,
    error            TEXT,
    UNIQUE (config_id, ordinal)
);

CREATE TABLE IF NOT EXISTS points (
    id            TEXT PRIMARY KEY,
    launch_id     TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,
    workload      TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('closed','open')),
    concurrency   INTEGER,
    request_rate  REAL,
    num_prompts   INTEGER NOT NULL,
    params        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS reps (
    id            TEXT PRIMARY KEY,
    point_id      TEXT NOT NULL REFERENCES points(id) ON DELETE CASCADE,
    rep           INTEGER NOT NULL,
    seed          INTEGER NOT NULL,
    started_at    REAL NOT NULL,
    duration_s    REAL,
    status        TEXT NOT NULL CHECK (status IN ('ok','failed','partial')),
    completed     INTEGER,
    failed        INTEGER,
    raw_path      TEXT,
    summary       TEXT NOT NULL DEFAULT '{}',
    tool_summary  TEXT NOT NULL DEFAULT '{}',
    gpu_before    TEXT,
    gpu_after     TEXT,
    UNIQUE (point_id, rep)
);
CREATE INDEX IF NOT EXISTS idx_reps_point ON reps (point_id);

CREATE TABLE IF NOT EXISTS quality_results (
    id           TEXT PRIMARY KEY,
    launch_id    TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,
    task         TEXT NOT NULL,
    n            INTEGER NOT NULL,
    metrics      TEXT NOT NULL,
    samples_path TEXT,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agreement_results (
    id                    TEXT PRIMARY KEY,
    launch_id             TEXT NOT NULL REFERENCES launches(id) ON DELETE CASCADE,
    reference_launch_id   TEXT NOT NULL REFERENCES launches(id),
    n                     INTEGER NOT NULL,
    exact_match_rate      REAL NOT NULL,
    mean_first_divergence REAL,
    samples_path          TEXT
);

CREATE TABLE IF NOT EXISTS regression_results (
    id                  TEXT PRIMARY KEY,
    experiment_id       TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    baseline_config_id  TEXT NOT NULL REFERENCES configs(id),
    candidate_config_id TEXT NOT NULL REFERENCES configs(id),
    workload            TEXT NOT NULL,
    point_key           TEXT NOT NULL,
    metric              TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('lower_better','higher_better')),
    effect_pct          REAL,
    ci_low              REAL,
    ci_high             REAL,
    p_value             REAL,
    p_adjusted          REAL,
    mde_pct             REAL,
    n_baseline          INTEGER NOT NULL,
    n_candidate         INTEGER NOT NULL,
    verdict             TEXT NOT NULL CHECK (verdict IN ('regression','improvement','no_change','inconclusive'))
);
CREATE INDEX IF NOT EXISTS idx_regress_cand ON regression_results (candidate_config_id, verdict);

CREATE TABLE IF NOT EXISTS recommendations (
    id               TEXT PRIMARY KEY,
    experiment_id    TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    constraints      TEXT NOT NULL,
    ranking          TEXT NOT NULL,
    chosen_config_id TEXT REFERENCES configs(id),
    created_at       REAL NOT NULL
);
