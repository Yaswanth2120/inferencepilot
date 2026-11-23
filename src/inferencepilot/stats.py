"""Pure-Python statistics on rep-level observations; no I/O or GPU dependencies."""

import math
import random
from dataclasses import dataclass
from itertools import combinations
from numbers import Real
from statistics import NormalDist


@dataclass(frozen=True)
class PermutationResult:
    p_value: float
    exact: bool
    permutations: int
    possible_permutations: int
    seed: int | None


@dataclass(frozen=True)
class MDEResult:
    mde_pct: float
    baseline_mean: float
    between_launch_variance: float
    within_launch_variance: float
    standard_error: float
    baseline_launches: int
    baseline_reps: int
    candidate_launches: int
    candidate_reps_per_launch: int
    alpha: float
    power: float


def _values(values, minimum=1):
    result = list(values)
    if len(result) < minimum:
        raise ValueError(f"at least {minimum} observations required")
    if any(
        isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
        for value in result
    ):
        raise ValueError("observations must be finite real numbers")
    return result


def _count(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _probability(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not 0 < value < 1:
        raise ValueError(f"{name} must be strictly between 0 and 1")


def mean(values):
    """Return the arithmetic mean of finite observations."""
    values = _values(values)
    return math.fsum(values) / len(values)


def percentile(values, percent):
    """Return a linear/type-7 percentile with percent on the 0–100 scale."""
    ordered = sorted(_values(values))
    if isinstance(percent, bool) or not isinstance(percent, Real) or not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    position = (len(ordered) - 1) * (percent / 100)
    lower = math.floor(position)
    upper = math.ceil(position)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def median(values):
    """Return the 50th percentile."""
    return percentile(values, 50)


def standard_deviation(values):
    """Return sample SD using the n-1 denominator."""
    values = _values(values, minimum=2)
    center = mean(values)
    return math.sqrt(math.fsum((value - center) ** 2 for value in values) / (len(values) - 1))


def coefficient_of_variation(values):
    """Return dimensionless sample SD divided by the absolute mean."""
    values = _values(values, minimum=2)
    center = mean(values)
    if center == 0:
        raise ValueError("coefficient of variation is undefined for a zero mean")
    return standard_deviation(values) / abs(center)


def bootstrap_ci(rep_values, confidence=0.95, resamples=10_000, seed=0):
    """Return (low, high) percentile-bootstrap bounds on the mean rep statistic."""
    values = _values(rep_values, minimum=2)
    _probability(confidence, "confidence")
    _count(resamples, "resamples")
    _count(seed, "seed", minimum=0)
    rng = random.Random(seed)
    estimates = [mean(rng.choices(values, k=len(values))) for _ in range(resamples)]
    tail = (1 - confidence) * 50
    return percentile(estimates, tail), percentile(estimates, 100 - tail)


def permutation_test(baseline, candidate, seed=0, exact_limit=20_000, monte_carlo_samples=100_000):
    """Test absolute mean difference using labeled rep assignments."""
    baseline = _values(baseline)
    candidate = _values(candidate)
    _count(seed, "seed", minimum=0)
    _count(exact_limit, "exact_limit")
    _count(monte_carlo_samples, "monte_carlo_samples")
    combined = baseline + candidate
    # Center before summing so a common large latency offset does not dominate ties.
    center = mean(combined)
    values = [value - center for value in combined]
    left_count, right_count = len(baseline), len(candidate)
    total = math.fsum(values)
    scale = 1 / left_count + 1 / right_count
    observed = abs(math.fsum(values[:left_count]) * scale - total / right_count)
    possible = math.comb(len(values), left_count)
    exact = possible <= exact_limit
    rng = random.Random(seed)
    assignments = (
        combinations(range(len(values)), left_count)
        if exact
        else (rng.sample(range(len(values)), left_count) for _ in range(monte_carlo_samples))
    )
    extreme = 0
    for indices in assignments:
        difference = abs(
            math.fsum(values[index] for index in indices) * scale - total / right_count
        )
        if difference >= observed or math.isclose(difference, observed, rel_tol=1e-12, abs_tol=0):
            extreme += 1
    evaluated = possible if exact else monte_carlo_samples
    # Include the observed assignment in randomized estimates; never report a simulated zero p.
    p_value = extreme / evaluated if exact else (extreme + 1) / (evaluated + 1)
    return PermutationResult(p_value, exact, evaluated, possible, None if exact else seed)


def holm_adjust(p_values):
    """Return Holm-adjusted probabilities in the original test order."""
    values = _values(p_values, minimum=0)
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError("p-values must be between 0 and 1")
    adjusted = [0.0] * len(values)
    previous = 0.0
    for rank, index in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        previous = min(1.0, max(previous, (len(values) - rank) * values[index]))
        adjusted[index] = previous
    return adjusted


def wilson_interval(successes, n, confidence=0.95):
    """Return a two-sided Wilson score interval without continuity correction."""
    _count(n, "n")
    _count(successes, "successes", minimum=0)
    _probability(confidence, "confidence")
    if successes > n:
        raise ValueError("successes cannot exceed n")
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def mcnemar_exact(baseline_only_correct, candidate_only_correct):
    """Return the exact two-sided binomial p-value from paired discordances."""
    _count(baseline_only_correct, "baseline_only_correct", minimum=0)
    _count(candidate_only_correct, "candidate_only_correct", minimum=0)
    discordant = baseline_only_correct + candidate_only_correct
    if discordant == 0:
        return 1.0
    shorter_tail = min(baseline_only_correct, candidate_only_correct)
    numerator = 2 * sum(math.comb(discordant, count) for count in range(shorter_tail + 1))
    return min(1.0, numerator / (1 << discordant))


def minimum_detectable_effect(
    baseline_launches, candidate_reps_per_launch=5, candidate_launches=1, alpha=0.05, power=0.80
):
    """Estimate percent MDE under the documented random-launch normal approximation."""
    launches = [_values(launch, minimum=2) for launch in baseline_launches]
    if len(launches) < 2:
        raise ValueError("at least two independent baseline launches required")
    _count(candidate_reps_per_launch, "candidate_reps_per_launch")
    _count(candidate_launches, "candidate_launches")
    _probability(alpha, "alpha")
    _probability(power, "power")
    if power <= 0.5:
        raise ValueError("power must be greater than 0.5 for the normal planning approximation")
    sizes = [len(launch) for launch in launches]
    count = sum(sizes)
    center = mean(value for launch in launches for value in launch)
    if center == 0:
        raise ValueError("percent MDE is undefined for a zero baseline mean")
    launch_means = [mean(launch) for launch in launches]
    within_ss = math.fsum(
        (value - launch_mean) ** 2
        for launch, launch_mean in zip(launches, launch_means)
        for value in launch
    )
    within = within_ss / (count - len(launches))
    between_ms = math.fsum(
        size * (launch_mean - center) ** 2 for size, launch_mean in zip(sizes, launch_means)
    ) / (len(launches) - 1)
    effective_size = (count - sum(size * size for size in sizes) / count) / (len(launches) - 1)
    between = max(0.0, (between_ms - within) / effective_size)
    baseline_launch_weight = sum((size / count) ** 2 for size in sizes)
    variance = between * (baseline_launch_weight + 1 / candidate_launches) + within * (
        1 / count + 1 / (candidate_launches * candidate_reps_per_launch)
    )
    standard_error = math.sqrt(variance)
    normal = NormalDist()
    multiplier = normal.inv_cdf(1 - alpha / 2) + normal.inv_cdf(power)
    effect = 100 * multiplier * standard_error / abs(center)
    return MDEResult(
        effect,
        center,
        between,
        within,
        standard_error,
        len(launches),
        count,
        candidate_launches,
        candidate_reps_per_launch,
        alpha,
        power,
    )


def bootstrap_effect_ci(baseline, candidate, confidence=0.95, resamples=10000, seed=0):
    """Independently resample reps to bound percent change relative to the resampled baseline."""
    a, b = _values(baseline), _values(candidate)
    _probability(confidence, "confidence")
    _count(resamples, "resamples")
    if any(value <= 0 for value in a):
        raise ValueError("percent effect bootstrap requires positive baseline observations")
    rng = random.Random(seed)
    effects = [
        100 * (mean(rng.choices(b, k=len(b))) / mean(rng.choices(a, k=len(a))) - 1)
        for _ in range(resamples)
    ]
    tail = (1 - confidence) * 50
    return percentile(effects, tail), percentile(effects, 100 - tail)
