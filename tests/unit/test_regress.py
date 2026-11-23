import pytest

from inferencepilot.regress import compare_family, summary, verdict
from inferencepilot.stats import bootstrap_effect_ci


@pytest.mark.parametrize(
    "effect,low,high,p,mde,nb,nc,direction,expected",
    [
        (5, 4, 6, 0.049, 5, 15, 5, "lower_better", "regression"),
        (-5, -6, -4, 0.049, 5, 15, 5, "lower_better", "improvement"),
        (-5, -6, -4, 0.049, 5, 15, 5, "higher_better", "regression"),
        (5, 4, 6, 0.049, 5, 15, 5, "higher_better", "improvement"),
        (5, 4, 6, 0.05, 5, 15, 5, "lower_better", "inconclusive"),
        (0, -5, 5, 1, 5, 15, 5, "lower_better", "no_change"),
        (0, -5.01, 5, 1, 5, 15, 5, "lower_better", "inconclusive"),
        (20, 19, 21, 0.001, 5.01, 15, 5, "lower_better", "inconclusive"),
        (20, 19, 21, 0.001, 1, 4, 5, "lower_better", "inconclusive"),
        (20, 19, 21, 0.001, 1, 15, 4, "lower_better", "inconclusive"),
        (None, None, None, 1, None, 15, 5, "lower_better", "inconclusive"),
    ],
)
def test_verdict_boundaries(effect, low, high, p, mde, nb, nc, direction, expected):
    assert verdict(effect, low, high, p, mde, nb, nc, direction) == expected


def test_effect_bootstrap_and_family():
    # Every resample of constant 100/110 has exactly a +10% effect.
    low, high = bootstrap_effect_ci([100] * 5, [110] * 5)
    assert low == pytest.approx(10) and high == pytest.approx(10)
    with pytest.raises(ValueError):
        bootstrap_effect_ci([0] * 5, [110] * 5)
    rows = compare_family(
        [
            dict(
                metric="latency",
                direction="lower_better",
                baseline=[[100] * 5] * 3,
                candidate=[[110] * 5],
            ),
            dict(
                metric="throughput",
                direction="higher_better",
                baseline=[[100] * 5] * 3,
                candidate=[[110] * 5],
            ),
        ]
    )
    assert rows[0]["verdict"] == "regression"
    assert rows[1]["verdict"] == "improvement"
    assert rows[0]["p_adjusted"] >= rows[0]["p_value"]
    assert summary(rows)["verdict"] == "regression"
    assert bootstrap_effect_ci([99, 100, 101], [102, 103, 104], seed=5) == bootstrap_effect_ci(
        [99, 100, 101], [102, 103, 104], seed=5
    )
