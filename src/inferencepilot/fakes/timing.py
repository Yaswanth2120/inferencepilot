"""Pure synthetic timing, independent of the HTTP framework."""

import random
from dataclasses import dataclass


@dataclass
class Settings:
    model: str = "fake-model"
    seed: int = 0
    healthy: bool = True
    token_delay: float = 0.001
    prefill_per_token: float = 0.0001
    concurrency_slowdown: float = 0.1
    jitter: float = 0.1
    inject_slowdown_pct: float = 0
    failure_rate: float = 0
    hang_rate: float = 0
    hang_seconds: float = 3600


def delays(settings, prompt_tokens, output_tokens, active, seed):
    rng = random.Random(settings.seed + seed)
    scale = (1 + settings.inject_slowdown_pct / 100) * (
        1 + settings.concurrency_slowdown * max(0, active - 1)
    )
    values = [settings.prefill_per_token * prompt_tokens] + [
        settings.token_delay for _ in range(output_tokens)
    ]
    return [
        max(0, value * scale * (1 + rng.uniform(-settings.jitter, settings.jitter)))
        for value in values
    ]
