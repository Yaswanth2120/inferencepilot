from dataclasses import replace
from pathlib import Path

import pytest

from inferencepilot.quality import (
    agreement,
    fixed_prompts,
    paired_quality,
    quality_command,
    quality_summary,
    read_samples,
)


def test_real_pinned_harness_sample_schema():
    path = Path(__file__).resolve().parents[1] / "fixtures/real/qwen3_lmeval_0492_samples.jsonl"
    samples = read_samples(path, expected_n=16)
    summary = quality_summary(samples)
    for kind in ("strict-match", "flexible-extract"):
        assert summary[kind]["n"] == 16
        assert summary[kind]["correct"] == 14
        assert summary[kind]["accuracy"] == 0.875
        assert paired_quality(samples, samples)[kind]["mcnemar_p"] == 1


def test_quality_command_snapshot():
    assert quality_command("Qwen/Qwen3-8B", 8000, "data/quality", limit=4, seed=7) == [
        "lm_eval",
        "--model",
        "local-completions",
        "--model_args",
        "model=Qwen/Qwen3-8B,base_url=http://127.0.0.1:8000/v1/completions,tokenized_requests=False,num_concurrent=1,max_retries=0",
        "--tasks",
        "gsm8k",
        "--num_fewshot",
        "5",
        "--log_samples",
        "--output_path",
        "data/quality",
        "--seed",
        "7",
        "--gen_kwargs",
        "do_sample=False,temperature=0,max_gen_toks=512",
        "--limit",
        "4",
    ]
    assert "--limit" not in quality_command("model", 8000, "out")
    with pytest.raises(ValueError):
        quality_command("model", 8000, "out", limit=0)


def test_sample_parser_and_paired_worked_values():
    samples = read_samples(
        Path(__file__).resolve().parents[1] / "fixtures/provisional/gsm8k_samples.jsonl", 4
    )
    summary = quality_summary(samples)
    # 3 correct out of 4; Wilson known interval .3006418426 to .9544127392.
    assert summary["flexible-extract"]["accuracy"] == 0.75
    assert summary["strict-match"]["ci_low"] == pytest.approx(0.3006418425824019)
    candidate = [replace(s, correct=False) for s in samples]
    paired = paired_quality(samples, candidate)
    # b=3,c=0 -> exact two-sided binomial p=2/2^3=.25, 75-point drop.
    assert paired["flexible-extract"]["mcnemar_p"] == 0.25
    assert paired["flexible-extract"]["drop_percentage_points"] == 75
    with pytest.raises(ValueError, match="hashes"):
        paired_quality(samples, [replace(s, prompt_hash="different") for s in candidate])
    with pytest.raises(ValueError):
        paired_quality(samples, candidate[:-1])
    with pytest.raises(ValueError):
        read_samples(
            Path(__file__).resolve().parents[1] / "fixtures/provisional/gsm8k_samples.jsonl", 3
        )


def test_agreement_worked_sequences():
    # One exact match; divergences at index 1 and prefix length 2 -> mean=1.5.
    result = agreement([[1, 2], [1, 2, 3], [4, 5]], [[1, 2], [1, 9, 3], [4, 5, 6]])
    assert result["exact_match_rate"] == 1 / 3 and result["n"] == 3
    assert result["mean_first_divergence"] == 1.5 and result["divergent_n"] == 2
    assert agreement([[1]], [[1]])["mean_first_divergence"] is None
    assert len(fixed_prompts()) == len(set(fixed_prompts())) == 200
    with pytest.raises(ValueError):
        agreement([[True]], [[1]])


def test_reject_duplicate_and_incomplete_filters():
    from inferencepilot.quality import parse_samples

    row = {
        "doc_id": 0,
        "doc_hash": "d",
        "prompt_hash": "p",
        "filter": "strict-match",
        "exact_match": 1,
    }
    with pytest.raises(ValueError, match="duplicate"):
        parse_samples([row, row])
    with pytest.raises(ValueError, match="both quality"):
        parse_samples([row])
