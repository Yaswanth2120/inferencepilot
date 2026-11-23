import asyncio

from inferencepilot.fakes.power import curve
from inferencepilot.regress import validate


def test_power_reproducible():
    first = asyncio.run(curve(trials=1, seed=7))
    assert first == asyncio.run(curve(trials=1, seed=7))
    assert [r["injected_slowdown_pct"] for r in first["results"]] == [2, 5, 10, 20]
    assert first["results"][0]["detected"] == 0
    assert first["results"][-1]["detected"] == 1
    assert all(r["n_trials"] == 1 for r in first["results"])


def test_aa_counted_and_between_launch_noise():
    import json

    records = {
        "configs": [{"id": "baseline", "role": "baseline"}],
        "experiment": {"seed": 42},
        "launches": [],
        "points": [],
        "reps": [],
    }
    for launch in range(3):
        identity = str(launch)
        records["launches"].append({"id": identity, "config_id": "baseline"})
        records["points"].append(
            dict(id=identity, launch_id=identity, workload="chat", mode="closed", concurrency=1)
        )
        for rep in range(5):
            # Large launch drift must produce a high MDE, not a false finding from pooled reps.
            value = 100 + launch * 20 + rep * 0.01
            records["reps"].append(
                dict(
                    point_id=identity,
                    status="ok",
                    summary=json.dumps(
                        dict(
                            request_throughput={"value": value},
                            output_throughput={"value": value},
                            distributions={"e2e": {"p95": value}},
                        )
                    ),
                )
            )
    result = validate(records)
    assert result["n_tests"] == 9
    assert result["false_positives"] == 0
    assert result["inconclusive"] == 9
    assert result["false_positive_rate"] == 0
