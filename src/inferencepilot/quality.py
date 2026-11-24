"""Raw-completion quality commands, paired sample statistics, and greedy token agreement."""

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from inferencepilot import stats

LM_EVAL_VERSION = "0.4.9.2"
FILTERS = ("strict-match", "flexible-extract")


@dataclass(frozen=True)
class QualitySample:
    doc_id: int
    doc_hash: str
    prompt_hash: str
    filter: str
    correct: bool


def quality_command(model, port, output_dir, limit=None, seed=0, binary="lm_eval"):
    if not model or any(char in model for char in ",\n\r"):
        raise ValueError("model must be a nonempty name without model_args delimiters")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("port must be in [1024,65535]")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
        raise ValueError("seed must be a nonnegative 32-bit integer")
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1319
    ):
        raise ValueError("quality limit must be the first N problems, 1<=N<=1319")
    args = [
        str(binary),
        "--model",
        "local-completions",
        "--model_args",
        f"model={model},base_url=http://127.0.0.1:{port}/v1/completions,tokenized_requests=False,num_concurrent=1,max_retries=0",
        "--tasks",
        "gsm8k",
        "--num_fewshot",
        "5",
        "--log_samples",
        "--output_path",
        str(output_dir),
        "--seed",
        str(seed),
        "--gen_kwargs",
        "do_sample=False,temperature=0,max_gen_toks=512",
    ]
    if limit is not None:
        args.extend(["--limit", str(limit)])
    return args


def parse_samples(rows, expected_n=None):
    samples = []
    keys = set()
    for row in rows:
        doc_id, kind = row.get("doc_id"), row.get("filter")
        score = row.get("exact_match")
        if (
            isinstance(doc_id, bool)
            or not isinstance(doc_id, int)
            or doc_id < 0
            or kind not in FILTERS
        ):
            raise ValueError("invalid lm-eval document/filter identity")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or score not in (0, 1):
            raise ValueError("exact_match must be binary numeric correctness")
        if not all(
            isinstance(row.get(field), str) and row[field] for field in ("doc_hash", "prompt_hash")
        ):
            raise ValueError("paired quality samples need document and prompt hashes")
        if (doc_id, kind) in keys:
            raise ValueError("duplicate quality sample")
        keys.add((doc_id, kind))
        samples.append(
            QualitySample(doc_id, row["doc_hash"], row["prompt_hash"], kind, bool(score))
        )
    identities = [{s.doc_id for s in samples if s.filter == kind} for kind in FILTERS]
    if not identities[0] or identities[0] != identities[1]:
        raise ValueError("both quality filters must cover identical nonempty documents")
    if expected_n is not None and identities[0] != set(range(expected_n)):
        raise ValueError("quality subset must be exactly the first expected_n dataset rows")
    return samples


def read_samples(path, expected_n=None):
    return parse_samples(
        [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()],
        expected_n,
    )


def quality_summary(samples):
    result = {}
    for kind in FILTERS:
        outcomes = [sample.correct for sample in samples if sample.filter == kind]
        if not outcomes:
            raise ValueError("quality summary requires both filters")
        correct, n = sum(outcomes), len(outcomes)
        low, high = stats.wilson_interval(correct, n)
        result[kind] = {
            "n": n,
            "correct": correct,
            "accuracy": correct / n,
            "ci_low": low,
            "ci_high": high,
        }
    return result


def paired_quality(baseline, candidate):
    reference = {(s.filter, s.doc_id): s for s in baseline}
    tested = {(s.filter, s.doc_id): s for s in candidate}
    if (
        len(reference) != len(baseline)
        or len(tested) != len(candidate)
        or reference.keys() != tested.keys()
    ):
        raise ValueError("paired samples must have identical unique document/filter keys")
    result = {}
    for kind in FILTERS:
        pairs = [(sample, tested[key]) for key, sample in reference.items() if key[0] == kind]
        if not pairs:
            raise ValueError("paired quality requires both filters")
        if any((a.doc_hash, a.prompt_hash) != (b.doc_hash, b.prompt_hash) for a, b in pairs):
            raise ValueError("paired quality document/prompt hashes differ")
        b = sum(a.correct and not c.correct for a, c in pairs)
        c = sum(not a.correct and candidate.correct for a, candidate in pairs)
        n = len(pairs)
        result[kind] = {
            "n": n,
            "baseline_only_correct": b,
            "candidate_only_correct": c,
            "drop_percentage_points": 100 * (b - c) / n,
            "mcnemar_p": stats.mcnemar_exact(b, c),
        }
    return result


def fixed_prompts():
    return [
        f"Answer briefly. Arithmetic problem {i}: What is {i} plus {(i * 7) % 29}?"
        for i in range(200)
    ]


def agreement(reference, candidate):
    if not reference or len(reference) != len(candidate):
        raise ValueError("agreement needs equally sized nonempty paired outputs")
    positions = []
    matches = 0
    for a, b in zip(reference, candidate):
        if any(
            isinstance(token, bool) or not isinstance(token, int) or token < 0 for token in [*a, *b]
        ):
            raise ValueError("agreement inputs must contain nonnegative integer token IDs")
        if a == b:
            matches += 1
            continue
        common = min(len(a), len(b))
        positions.append(next((i for i in range(common) if a[i] != b[i]), common))
    return {
        "n": len(reference),
        "exact_matches": matches,
        "exact_match_rate": matches / len(reference),
        "divergent_n": len(positions),
        "mean_first_divergence": stats.mean(positions) if positions else None,
        "position_convention": "zero-based; shorter length for a strict prefix; matching outputs excluded",
    }


async def greedy_outputs(client, model, prompts, max_tokens=64, seed=0):
    if not prompts or any(not isinstance(prompt, str) or not prompt for prompt in prompts):
        raise ValueError("nonempty fixed prompts required")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    outputs = []
    for prompt in prompts:
        response = await client.post(
            "/v1/completions",
            json={
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0,
                "seed": seed,
                "stream": False,
                "logprobs": 1,
                "return_tokens_as_token_ids": True,
            },
        )
        response.raise_for_status()
        payload = response.json()
        try:
            tokens = payload["choices"][0]["logprobs"]["tokens"]
            ids = [
                int(token.removeprefix("token_id:"))
                for token in tokens
                if isinstance(token, str) and token.startswith("token_id:")
            ]
            if len(ids) != len(tokens) or not ids or any(token < 0 for token in ids):
                raise ValueError("missing generated token IDs")
            if payload["usage"]["completion_tokens"] != len(ids):
                raise ValueError("token ID count differs from completion usage")
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError(
                "agreement requires complete returned token IDs, not decoded text"
            ) from error
        outputs.append(ids)
    return outputs


async def agreement_check(
    base_url, model, reference_outputs=None, prompts=None, max_tokens=64, seed=0
):
    prompts = fixed_prompts() if prompts is None else prompts
    async with httpx.AsyncClient(base_url=base_url, timeout=60, trust_env=False) as client:
        outputs = await greedy_outputs(client, model, prompts, max_tokens, seed)
    return outputs, agreement(reference_outputs, outputs) if reference_outputs is not None else None


def evaluation_key(spec, role, config_id, limit):
    """Share scheduling-only quality evidence; combined candidates get their own evaluation."""
    import hashlib

    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1319
    ):
        raise ValueError("quality limit must be the first N problems, 1<=N<=1319")
    fields = (
        "variant",
        "model",
        "quantization",
        "dtype",
        "kv_cache_dtype",
        "max_model_len",
        "seed",
    )
    identity = {name: getattr(spec, name) for name in fields}
    identity.update(
        task="gsm8k",
        harness_version=LM_EVAL_VERSION,
        subset=limit or 1319,
        fewshot=5,
        max_gen_tokens=512,
    )
    if role == "combined":
        identity.update(combined_config_id=config_id, full_spec=spec.model_dump())
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
