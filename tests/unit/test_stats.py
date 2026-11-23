import ast
import math
import random
from pathlib import Path

import pytest

from inferencepilot import stats


@pytest.mark.parametrize(
    "values,percent,expected",
    [
        # NumPy default/type 7: h=(n-1)*p/100, interpolate between floor(h) and ceil(h).
        ([7], 99, 7),  # h=0, singleton stays 7.
        ([0, 10], 25, 2.5),  # h=.25, 0*.75+10*.25=2.5.
        ([1, 2, 3, 4], 95, 3.85),  # h=2.85, 3*.15+4*.85=3.85.
        ([9, 1, 5, 3, 7], 50, 5),  # sorted 1,3,5,7,9; h=2.
        ([0, 0, 10, 10, 20], 99, 19.6),  # h=3.96, 10*.04+20*.96=19.6.
        ([-10, -2, 2, 10], 25, -4),  # h=.75, -10*.25-2*.75=-4.
        ([2, 9], 0, 2),  # h=0.
        ([2, 9], 100, 9),  # h=1.
        ([-1e308, 1e308], 50, 0),  # convex interpolation avoids b-a overflow.
    ],
)
def test_percentile_worked_arrays(values, percent, expected):
    assert stats.percentile(values, percent) == pytest.approx(expected)


def test_descriptive_worked_values():
    # 1+2+3+4=10, mean=2.5, even median=(2+3)/2=2.5.
    # Squared deviations 2.25+.25+.25+2.25=5; sample variance=5/3.
    assert stats.mean([1, 2, 3, 4]) == 2.5
    assert stats.median([4, 1, 3, 2]) == 2.5
    assert stats.median([3, 1, 2]) == 2
    assert stats.standard_deviation([1, 2, 3, 4]) == pytest.approx(math.sqrt(5 / 3))
    assert stats.coefficient_of_variation([1, 2, 3, 4]) == pytest.approx(math.sqrt(5 / 3) / 2.5)
    # Negative mean uses its magnitude: [-3,-1] has mean -2 and sample SD sqrt(2).
    assert stats.coefficient_of_variation([-3, -1]) == pytest.approx(math.sqrt(2) / 2)
    assert stats.standard_deviation([7, 7]) == 0
    # fsum retains the middle 1 despite cancellation; arithmetic mean is 1/3.
    assert stats.mean([1e16, 1, -1e16]) == pytest.approx(1 / 3)


def test_bootstrap_worked_seed_and_reproducibility():
    # Seed 0 uniform draws for [0,2] fall in bins: (1,1),(0,0),(1,0),(1,0).
    # Resampled means [2,0,1,1], sorted [0,1,1,2]. A 50% CI uses h=.75,2.25.
    assert stats.bootstrap_ci([0, 2], confidence=0.5, resamples=4, seed=0) == (0.75, 1.25)
    # Seed 2 draws bins (1,1),(0,0),(1,1),(1,0): means [2,0,2,1].
    assert stats.bootstrap_ci([0, 2], confidence=0.5, resamples=4, seed=2) == (0.75, 2)
    # The exact two-observation bootstrap distribution is 0,1,2 with masses 1/4,1/2,1/4.
    # With 10,000 seeded draws, the 2.5% and 97.5% quantiles are the endpoints 0 and 2.
    first = stats.bootstrap_ci([0, 2])
    assert first == stats.bootstrap_ci([0, 2]) == (0, 2)
    # A constant rep statistic has a point interval regardless of resampling.
    assert stats.bootstrap_ci([7, 7, 7], resamples=10) == (7, 7)


def test_resampling_does_not_mutate_global_rng_or_inputs():
    # Constant values have a [3,3] interval and all tied permutations have p=1.
    baseline = [3, 3]
    before = list(baseline)
    state = random.getstate()
    assert stats.bootstrap_ci(baseline, resamples=4) == (3, 3)
    assert (
        stats.permutation_test(baseline, baseline, exact_limit=1, monte_carlo_samples=4).p_value
        == 1
    )
    assert random.getstate() == state
    assert baseline == before


def test_exact_permutation_enumerated_by_hand():
    # For pooled [1,2,3,4], choose 2 labeled positions. The six subsets have
    # absolute mean differences: {1,2}:2, {1,3}:1, {1,4}:0, {2,3}:0, {2,4}:1, {3,4}:2.
    # Observed 2 is matched/exceeded twice: p=2/6, with no Monte Carlo +1 correction.
    result = stats.permutation_test([1, 2], [3, 4])
    assert result.p_value == pytest.approx(1 / 3)
    assert result.exact and result.permutations == result.possible_permutations == 6
    assert result.seed is None
    # Duplicates remain labeled positions. [0,0] vs [1,1] also has 2 extreme of 6.
    assert stats.permutation_test([0, 0], [1, 1]).p_value == pytest.approx(1 / 3)
    assert stats.permutation_test([3, 4], [1, 2]).p_value == result.p_value
    # Shifting both groups by 10^9 preserves the six mean differences.
    assert stats.permutation_test([1e9 + 1, 1e9 + 2], [1e9 + 3, 1e9 + 4]).p_value == result.p_value
    # Scaling by tiny units must not turn genuinely different statistics into ties.
    assert stats.permutation_test([1e-20, 2e-20], [3e-20, 4e-20]).p_value == result.p_value


def test_monte_carlo_worked_draws():
    # Force MC on the same six partitions. Seed 0 picks indices:
    # (3,1),(0,1),(3,1),(2,1),(2,3),(1,2): differences 1,2,1,0,2,0.
    # Two extremes in six draws -> conservative (2+1)/(6+1)=3/7.
    result = stats.permutation_test([1, 2], [3, 4], exact_limit=1, monte_carlo_samples=6)
    assert not result.exact and result.p_value == pytest.approx(3 / 7)
    assert result.permutations == 6 and result.possible_permutations == 6 and result.seed == 0
    assert result == stats.permutation_test([1, 2], [3, 4], exact_limit=1, monte_carlo_samples=6)
    # A single seed-0 draw is non-extreme, but the p-value is (0+1)/(1+1)=1/2, not zero.
    assert (
        stats.permutation_test([1, 2], [3, 4], exact_limit=1, monte_carlo_samples=1).p_value == 0.5
    )


def test_permutation_default_method_boundary():
    # C(16,8)=12870 <=20000: enumerate; C(17,8)=24310 >20000: 100000 draws.
    # All observations equal 7, hence every distance equals 0 and p=1 in either mode.
    exact = stats.permutation_test([7] * 8, [7] * 8)
    sampled = stats.permutation_test([7] * 8, [7] * 9)
    assert exact.exact and exact.permutations == 12870 and exact.p_value == 1
    assert not sampled.exact and sampled.possible_permutations == 24310
    assert sampled.permutations == 100_000 and sampled.p_value == 1


def test_holm_worked_example():
    # Input [.04,.01,.03,.2], sorted .01,.03,.04,.2 -> raw adjusted .04,.09,.08,.2.
    # Running maximum .04,.09,.09,.2; restoring original order -> .09,.04,.09,.2.
    assert stats.holm_adjust([0.04, 0.01, 0.03, 0.2]) == pytest.approx([0.09, 0.04, 0.09, 0.2])
    # Tied .01 entries: multipliers 3 and 2 become .03,.03 after monotonicity.
    assert stats.holm_adjust([0.01, 0.01, 0.9]) == pytest.approx([0.03, 0.03, 0.9])
    assert stats.holm_adjust([0.8, 0.9]) == [1, 1]  # clipping at 1.
    assert stats.holm_adjust([0, 1]) == [0, 1]
    assert stats.holm_adjust([]) == []


def test_wilson_worked_values():
    # x=5,n=10,p=.5,z=1.959963984540054; center=.5 and
    # radius=z*sqrt(.25/10+z^2/400)/(1+z^2/10)=.263406909487436.
    assert stats.wilson_interval(5, 10) == pytest.approx((0.236593090512564, 0.763406909487436))
    # For x=0, the upper bound is z^2/(n+z^2)=.277532799862889; x=n is symmetric.
    assert stats.wilson_interval(0, 10) == pytest.approx((0, 0.277532799862889))
    assert stats.wilson_interval(10, 10) == pytest.approx((0.722467200137111, 1))
    # 68.268949...% central normal confidence has z=1. x=1,n=2 gives .5 +/- sqrt(3)/6.
    assert stats.wilson_interval(1, 2, confidence=0.6826894921370859) == pytest.approx(
        (0.5 - math.sqrt(3) / 6, 0.5 + math.sqrt(3) / 6)
    )


def test_mcnemar_worked_tables():
    # Table [[20,1],[7,12]]: only b=1,c=7 matter. B~Binomial(8,.5).
    # Two-sided exact p=2*(C(8,0)+C(8,1))/2^8=18/256=.0703125.
    assert stats.mcnemar_exact(1, 7) == 18 / 256
    assert stats.mcnemar_exact(7, 1) == 18 / 256
    # b=0,c=6 -> 2*C(6,0)/2^6=1/32; no discordances -> p=1.
    assert stats.mcnemar_exact(0, 6) == 1 / 32
    assert stats.mcnemar_exact(0, 0) == 1
    assert stats.mcnemar_exact(3, 3) == 1  # doubled lower-tail is capped at 1.
    # n=1400 exceeds float exponent range, but the integer-ratio tail remains valid.
    assert stats.mcnemar_exact(700, 700) == 1


def test_mde_balanced_worked_components():
    # Three launches, two reps: means 9,11,13; grand mean 11.
    # Within SS=6, df=3 -> sigma^2=2. Between SS=16, df=2 -> MSB=8.
    # tau^2=(8-2)/2=3. Candidate one launch with two reps:
    # V=3*(1/3+1)+2*(1/6+1/2)=16/3. z(.975)+z(.8)=2.801585218112968.
    result = stats.minimum_detectable_effect(
        [[8, 10], [10, 12], [12, 14]], candidate_reps_per_launch=2
    )
    assert result.baseline_mean == 11
    assert result.within_launch_variance == 2
    assert result.between_launch_variance == 3
    assert result.standard_error == pytest.approx(math.sqrt(16 / 3))
    assert result.mde_pct == pytest.approx(100 * 2.801585218112968 * math.sqrt(16 / 3) / 11)
    assert result.baseline_launches == 3 and result.baseline_reps == 6
    assert result.candidate_launches == 1 and result.candidate_reps_per_launch == 2
    assert result.alpha == 0.05 and result.power == 0.80


def test_mde_unbalanced_worked_components():
    # Sizes 2,3,2; means 9,12,13; grand mean 80/7.
    # Within SS=12, df=4 -> sigma^2=3. Between MS=(124/7)/2=62/7.
    # n0=(7-17/7)/2=16/7, so tau^2=((62/7)-3)/(16/7)=41/16.
    # Baseline launch weights sum of squares=17/49. For candidate r=2,c=1:
    # V=(41/16)*(17/49+1)+3*(1/7+1/2)=2109/392.
    result = stats.minimum_detectable_effect(
        [[8, 10], [10, 12, 14], [12, 14]], candidate_reps_per_launch=2
    )
    assert result.baseline_mean == pytest.approx(80 / 7)
    assert result.within_launch_variance == 3
    assert result.between_launch_variance == pytest.approx(41 / 16)
    assert result.standard_error == pytest.approx(math.sqrt(2109 / 392))
    assert result.mde_pct == pytest.approx(
        100 * 2.801585218112968 * math.sqrt(2109 / 392) / (80 / 7)
    )


def test_mde_zero_clipping_scaling_and_replication():
    # Identical launch means: MSB=0, MSW=8; negative tau^2 is clipped to zero.
    result = stats.minimum_detectable_effect([[8, 12]] * 3, candidate_reps_per_launch=2)
    assert result.between_launch_variance == 0 and result.within_launch_variance == 8
    assert result.standard_error == pytest.approx(math.sqrt(16 / 3))
    # Constant measurements have both variance components zero and estimated MDE=0.
    assert stats.minimum_detectable_effect([[10, 10]] * 3).mde_pct == 0
    launches = [[8, 10], [10, 12], [12, 14]]
    baseline = stats.minimum_detectable_effect(launches)
    # Multiplying every datum by 10 scales SD and mean equally, leaving percent MDE unchanged.
    assert stats.minimum_detectable_effect(
        [[v * 10 for v in launch] for launch in launches]
    ).mde_pct == (pytest.approx(baseline.mde_pct))
    # Between-launch tau^2=3: more reps cannot remove 3*(1/3+1)=4 variance.
    more_reps = stats.minimum_detectable_effect(launches, candidate_reps_per_launch=1_000_000)
    assert more_reps.standard_error**2 >= 4
    assert more_reps.mde_pct < baseline.mde_pct
    assert (
        stats.minimum_detectable_effect(launches, candidate_launches=2).mde_pct < baseline.mde_pct
    )
    assert stats.minimum_detectable_effect(launches, power=0.9).mde_pct > baseline.mde_pct
    assert stats.minimum_detectable_effect(launches, alpha=0.01).mde_pct > baseline.mde_pct


@pytest.mark.parametrize("values", [[], [1, float("nan")], [float("inf")], ["1"], [True]])
def test_invalid_observations(values):
    with pytest.raises(ValueError):
        stats.mean(values)


@pytest.mark.parametrize("percent", [-1, 101, float("nan"), float("inf"), "50", True])
def test_invalid_percentiles(percent):
    with pytest.raises(ValueError, match="percent"):
        stats.percentile([1, 2], percent)


def test_insufficient_data_and_zero_mean():
    with pytest.raises(ValueError, match="at least 2"):
        stats.standard_deviation([1])
    with pytest.raises(ValueError, match="zero mean"):
        stats.coefficient_of_variation([-1, 1])
    with pytest.raises(ValueError, match="at least 2"):
        stats.bootstrap_ci([1])
    with pytest.raises(ValueError, match="at least 1"):
        stats.permutation_test([], [1])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"confidence": 0},
        {"confidence": 1},
        {"resamples": 0},
        {"resamples": 1.5},
        {"seed": -1},
        {"seed": True},
    ],
)
def test_invalid_bootstrap_parameters(kwargs):
    with pytest.raises(ValueError):
        stats.bootstrap_ci([1, 2], **kwargs)


@pytest.mark.parametrize("kwargs", [{"exact_limit": 0}, {"monte_carlo_samples": 0}, {"seed": -1}])
def test_invalid_permutation_parameters(kwargs):
    with pytest.raises(ValueError):
        stats.permutation_test([1], [2], **kwargs)


@pytest.mark.parametrize("pvalues", [[-0.1], [1.1], [float("nan")], [None]])
def test_invalid_holm_probabilities(pvalues):
    with pytest.raises(ValueError):
        stats.holm_adjust(pvalues)


@pytest.mark.parametrize(
    "successes,n,confidence",
    [
        (-1, 10, 0.95),
        (11, 10, 0.95),
        (1, 0, 0.95),
        (1.5, 10, 0.95),
        (True, 10, 0.95),
        (1, 10, float("nan")),
        (1, 10, 1),
    ],
)
def test_invalid_wilson_inputs(successes, n, confidence):
    with pytest.raises(ValueError):
        stats.wilson_interval(successes, n, confidence)


@pytest.mark.parametrize("b,c", [(-1, 1), (1, -1), (1.2, 2), (True, 2)])
def test_invalid_mcnemar_counts(b, c):
    with pytest.raises(ValueError):
        stats.mcnemar_exact(b, c)


@pytest.mark.parametrize(
    "launches,kwargs",
    [
        ([[1, 2]], {}),
        ([[1], [2]], {}),
        ([[float("nan"), 2], [1, 2]], {}),
        ([[-1, 1], [-1, 1]], {}),
        ([[1, 2], [2, 3]], {"candidate_launches": 0}),
        ([[1, 2], [2, 3]], {"candidate_reps_per_launch": 0}),
        ([[1, 2], [2, 3]], {"alpha": 0}),
        ([[1, 2], [2, 3]], {"power": 1}),
        ([[1, 2], [2, 3]], {"power": 0.5}),
    ],
)
def test_invalid_mde_inputs(launches, kwargs):
    with pytest.raises(ValueError):
        stats.minimum_detectable_effect(launches, **kwargs)


def test_source_has_no_numpy_imports():
    # The entire src tree must stay independent of NumPy, including future modules.
    for path in (Path(__file__).resolve().parents[2] / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] != "numpy" for alias in node.names), str(path)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "numpy", str(path)
