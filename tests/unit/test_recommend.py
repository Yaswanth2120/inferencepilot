import copy

import pytest

from inferencepilot.recommend import Constraints, recommend
from inferencepilot.report import number

CONSTRAINTS = dict(
    points={"chat:closed:1": {"p95_ttft": 5, "p95_e2e": 50}}, objective={"point": "chat:closed:1"}
)


def candidate(identity, throughput, e2e, accuracy=0.8):
    return dict(
        id=identity,
        label=identity,
        points={
            "chat:closed:1": {
                "p95_ttft": {"mean": 2, "n_reps": 5},
                "p95_e2e": {"mean": e2e, "n_reps": 5},
                "output_throughput": {"mean": throughput, "n_reps": 5},
            }
        },
        quality={"n": 100, "accuracy": accuracy, "drop_pp": 0, "mcnemar_p": 1},
    )


def test_constraint_ranking_and_pareto():
    # A dominates B; C trades lower throughput for shorter E2E; D breaches the SLO by 10 ms.
    a, b, c, d = (
        candidate("a", 100, 20),
        candidate("b", 90, 25),
        candidate("c", 80, 10),
        candidate("d", 200, 60),
    )
    result = recommend([a, b, c, d], CONSTRAINTS)
    assert result["chosen_config_id"] == "a"
    assert result["pareto"] == ["a", "c"]
    assert "by 10 ms" in result["rejected"][0]["reasons"][0]
    assert result["description"] == "best tested configuration under these constraints"


def test_quality_and_missing_evidence_reasons():
    a = candidate("a", 100, 20)
    a["quality"].update(drop_pp=1.1, mcnemar_p=0.049)
    b = candidate("b", 100, 20)
    b["quality"] = None
    del b["points"]["chat:closed:1"]["p95_ttft"]
    result = recommend([a, b], CONSTRAINTS)
    assert result["chosen_config_id"] is None
    reasons = result["rejected"][0]["reasons"]
    assert "exceeds 1 pp by 0.1 pp" in reasons[0]
    assert "McNemar p=0.049 below 0.05" in reasons[1]
    assert "Missing paired" in result["rejected"][1]["reasons"][0]
    a["quality"].update(drop_pp=1, mcnemar_p=0.05)
    assert recommend([a], CONSTRAINTS)["chosen_config_id"] == "a"


@pytest.mark.parametrize("n", [None, 0, -1, True, 1.5])
def test_number_requires_n(n):
    with pytest.raises(ValueError, match="positive n"):
        number(100, n)


def test_invalid_constraints_and_nonfinite_number():
    with pytest.raises(ValueError):
        number(float("nan"), 5)
    constraints = copy.deepcopy(CONSTRAINTS)
    constraints["points"]["chat:closed:1"]["unknown"] = 2
    with pytest.raises(ValueError):
        Constraints.model_validate(constraints)
