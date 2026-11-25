import json

import pytest

from inferencepilot import analysis
from inferencepilot.config import VARIANTS, ConfigSpec


@pytest.mark.parametrize("online_score,checkpoint_score", [(130, 120), (120, 130), (90, 95)])
@pytest.mark.parametrize("reverse", [False, True])
def test_combined_precision_is_one_observed_tuple(
    monkeypatch, online_score, checkpoint_score, reverse
):
    baseline = ConfigSpec()
    specs = {"baseline": baseline}
    for variant in ("fp8_online", "fp8_ckpt"):
        model, quantization = VARIANTS[variant]
        specs[variant] = ConfigSpec(variant=variant, model=model, quantization=quantization)
    specs["scheduling"] = ConfigSpec(max_num_seqs=64)
    scores = {
        "baseline": 100,
        "fp8_online": online_score,
        "fp8_ckpt": checkpoint_score,
        "scheduling": 110,
    }
    identities = list(specs)
    if reverse:
        identities.reverse()
    records = {
        "configs": [
            dict(
                id=key,
                role="baseline" if key == "baseline" else "candidate",
                spec=specs[key].model_dump_json(),
            )
            for key in identities
        ]
    }
    grouped = {
        (key, "chat:closed:64", "output_throughput"): {key: [scores[key]] * 5} for key in identities
    }
    monkeypatch.setattr(analysis, "observations", lambda records: grouped)
    combined = analysis.combined_spec(records, baseline)
    winner = max(("baseline", "fp8_online", "fp8_ckpt"), key=lambda key: scores[key])
    assert (combined.variant, combined.model, combined.quantization) == (
        specs[winner].variant,
        specs[winner].model,
        specs[winner].quantization,
    )
    assert combined.max_num_seqs == 64
    assert json.loads(combined.model_dump_json())["model"] == specs[winner].model
