import json

import pytest

from inferencepilot import report
from inferencepilot.fakes.selftest import synthetic_constraints
from inferencepilot.recommend import recommend
from inferencepilot.store import Store


def test_report_from_persisted_experiment(tmp_path):
    # The subprocess interruption test already creates a complete campaign. Here a separate
    # small persisted evidence set tests the renderer without replaying an identical server test.
    from inferencepilot.fakes.selftest import mini_plan

    store = Store(tmp_path / "experiment.db")
    identity = store.create(mini_plan(), {"gpu": "FAKE synthetic environment"}, 14)
    bundle = dict(
        experiment=store.rows("experiments", id=identity)[0],
        records=store.records(identity),
        environment={"gpu": "FAKE"},
        aggregates=[],
        regressions=[],
        validation={"false_positives": 0, "n_tests": 0, "inconclusive": 0},
        recommendation=recommend([], synthetic_constraints()),
        live="not run (needs GPU)",
        measurement_notes=["SYNTHETIC"],
    )
    files = report.write(bundle, tmp_path / "reports")
    assert "report.md" in files and "report.json" in files
    text = (tmp_path / "reports/report.md").read_text()
    for expected in (
        "Environment",
        "Requested and resolved",
        "Per-workload",
        "Regression evidence",
        "Quality and McNemar",
        "Greedy token agreement",
        "Recommendation",
    ):
        assert expected in text
    assert json.loads((tmp_path / "reports/report.json").read_text()) == bundle
    bundle["aggregates"] = [
        dict(
            config_id=bundle["records"]["configs"][0]["id"],
            point="chat:closed:1",
            metric="p95_e2e",
            mean=20,
            n_reps=0,
            ci_low=19,
            ci_high=21,
            n_launches=1,
        )
    ]
    with pytest.raises(ValueError, match="positive n"):
        report.write(bundle, tmp_path / "invalid")
    store.close()
