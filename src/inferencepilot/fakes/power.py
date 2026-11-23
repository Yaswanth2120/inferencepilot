"""Repeated fake HTTP timing experiments. These are model-based, never GPU evidence."""

import argparse
import asyncio
import json
import random
from pathlib import Path

import httpx

from inferencepilot import stats
from inferencepilot.fakes.fake_vllm import Settings, create_app
from inferencepilot.regress import compare_family


async def simulated_launch(seed, slowdown):
    rng = random.Random(seed)
    settings = Settings(
        seed=seed, jitter=0.005, inject_slowdown_pct=slowdown + rng.uniform(-0.2, 0.2)
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://fake"
    ) as client:
        values = []
        for rep in range(5):
            response = await client.get("/fake/timing", params={"seed": rep})
            response.raise_for_status()
            values.append(response.json()["seconds"])
    return values


async def curve(trials=20, seed=1729):
    results = []
    for effect in (2, 5, 10, 20):
        detected = 0
        for trial in range(trials):
            launches = [
                await simulated_launch(seed + trial * 10 + launch, 0) for launch in range(3)
            ]
            candidate = await simulated_launch(seed + trial * 10 + 3, effect)
            row = compare_family(
                [
                    dict(
                        metric="e2e",
                        direction="lower_better",
                        baseline=launches,
                        candidate=[candidate],
                    )
                ],
                seed=seed + trial,
            )[0]
            detected += row["verdict"] == "regression"
        low, high = stats.wilson_interval(detected, trials)
        results.append(
            dict(
                injected_slowdown_pct=effect,
                detected=detected,
                n_trials=trials,
                detection_rate=detected / trials,
                ci_low=low,
                ci_high=high,
            )
        )
    return dict(
        kind="SYNTHETIC fake-server timing model; not GPU results",
        seed=seed,
        min_effect_pct=5,
        baseline_launches=3,
        reps_per_launch=5,
        launch_noise_uniform_pp=[-0.2, 0.2],
        token_jitter_fraction=0.005,
        method="HTTP ASGI fake timing endpoint; independently seeded launches; detector defaults; 10000 bootstrap resamples",
        limitation="One metric per family; real multi-metric family correction and real GPU noise may reduce power. Below-threshold effects intentionally do not count as regressions.",
        results=results,
        live="not run (needs GPU)",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asyncio.run(curve(args.trials)), indent=2, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
