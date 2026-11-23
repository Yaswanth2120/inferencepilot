"""Constraint filtering and Pareto ranking over already analyzed evidence."""

from pydantic import Field, model_validator

from inferencepilot.config import SLOSpec, Spec


class QualityConstraint(Spec):
    filter: str = "flexible-extract"
    max_drop_pp: float = Field(default=1, ge=0)
    min_mcnemar_p: float = Field(default=0.05, ge=0, le=1)


class Objective(Spec):
    point: str
    metric: str = "output_throughput"


class Constraints(Spec):
    points: dict[str, dict[str, float]]
    quality: QualityConstraint = Field(default_factory=QualityConstraint)
    objective: Objective
    request_slos: dict[str, SLOSpec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid(self):
        if self.objective.metric != "output_throughput":
            raise ValueError("objective must maximize output_throughput")
        if self.objective.point not in self.points:
            raise ValueError("objective point must have stated SLO constraints")
        if self.quality.filter not in ("strict-match", "flexible-extract"):
            raise ValueError("unknown quality filter")
        for limits in self.points.values():
            if not limits or any(
                k not in ("p95_ttft", "p95_e2e", "p95_tpot_per_request") or v < 0
                for k, v in limits.items()
            ):
                raise ValueError("SLOs require nonnegative p95 latency limits in milliseconds")
        return self


def dominates(a, b):
    return (
        a["throughput"] >= b["throughput"]
        and a["e2e"] <= b["e2e"]
        and a["quality"] >= b["quality"]
        and (
            a["throughput"] > b["throughput"] or a["e2e"] < b["e2e"] or a["quality"] > b["quality"]
        )
    )


def recommend(candidates, constraints):
    """Filter measured candidates, then rank survivors and retain non-dominated choices."""
    constraints = Constraints.model_validate(constraints)
    accepted, rejected = [], []
    for candidate in candidates:
        reasons = list(candidate.get("errors", []))
        evidence = candidate.get("quality")
        if evidence is None:
            reasons.append("Missing paired gsm8k quality evidence")
        else:
            if evidence["n"] <= 0:
                reasons.append("Quality sample count must be positive")
            if evidence["drop_pp"] > constraints.quality.max_drop_pp:
                reasons.append(
                    f"Quality drop {evidence['drop_pp']:.6g} pp exceeds {constraints.quality.max_drop_pp:g} pp by {evidence['drop_pp'] - constraints.quality.max_drop_pp:.6g} pp (n={evidence['n']})"
                )
            if evidence["mcnemar_p"] < constraints.quality.min_mcnemar_p:
                reasons.append(
                    f"McNemar p={evidence['mcnemar_p']:.6g} below {constraints.quality.min_mcnemar_p:g} (n={evidence['n']})"
                )
        for point, limits in constraints.points.items():
            for metric, limit in limits.items():
                measured = candidate.get("points", {}).get(point, {}).get(metric)
                if measured is None or measured.get("n_reps", 0) < 5:
                    reasons.append(f"Missing five comparable reps for {point} {metric}")
                elif measured["mean"] > limit:
                    reasons.append(
                        f"{point} {metric}={measured['mean']:.6g} ms exceeds {limit:g} ms by {measured['mean'] - limit:.6g} ms (n_reps={measured['n_reps']})"
                    )
        target = candidate.get("points", {}).get(constraints.objective.point, {})
        throughput, e2e = target.get("output_throughput"), target.get("p95_e2e")
        if not throughput or not e2e or min(throughput.get("n_reps", 0), e2e.get("n_reps", 0)) < 5:
            reasons.append("Objective throughput and p95 E2E need five comparable reps")
        if reasons:
            rejected.append(
                {"config_id": candidate["id"], "label": candidate["label"], "reasons": reasons}
            )
        else:
            accepted.append(
                dict(
                    config_id=candidate["id"],
                    label=candidate["label"],
                    throughput=throughput["mean"],
                    e2e=e2e["mean"],
                    quality=evidence["accuracy"],
                    n_reps=throughput["n_reps"],
                    quality_n=evidence["n"],
                    warnings=candidate.get("warnings", []),
                )
            )
    accepted.sort(key=lambda c: (-c["throughput"], c["label"]))
    pareto = [
        c["config_id"] for c in accepted if not any(dominates(other, c) for other in accepted)
    ]
    return dict(
        description="best tested configuration under these constraints",
        chosen_config_id=accepted[0]["config_id"] if accepted else None,
        ranking=accepted,
        pareto=pareto,
        rejected=rejected,
        constraints=constraints.model_dump(),
        policy="SLOs compare the mean of rep p95 values against limits; intervals are reported separately. Ranking is observed, not a claim of significant superiority.",
        limitations=[
            "Only tested configurations qualify; OFAT interactions are checked only in the combined run.",
            "Quality non-significance is a constraint, not proof of equivalence.",
        ],
    )
