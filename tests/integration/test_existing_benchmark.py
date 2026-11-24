import argparse
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from inferencepilot import env
from inferencepilot.store import Store
from inferencepilot.vllm_flags import BENCH_FLAGS

SCRIPT = Path(__file__).parents[2] / "scripts/benchmark_existing.py"


def load_script():
    spec = importlib.util.spec_from_file_location("existing_benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_endpoint_identity_and_context():
    module = load_script()
    payload = {"data": [{"id": "openai/gpt-oss-120b", "max_model_len": 8192}]}
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
        base_url="http://localhost",
    ) as client:
        assert module.endpoint(client, "openai/gpt-oss-120b")["max_model_len"] == 8192
        with pytest.raises(ValueError, match="matching model"):
            module.endpoint(client, "wrong-model")


def test_checkpointed_existing_benchmark(tmp_path, monkeypatch):
    module = load_script()
    monkeypatch.setattr(
        module, "endpoint", lambda client, model: {"id": model, "max_model_len": 8192}
    )
    monkeypatch.setattr(env, "snapshot", lambda: {"scope": "SYNTHETIC integration test"})
    monkeypatch.setattr(
        env,
        "command_output",
        lambda argv: {"available": True, "output": " ".join(BENCH_FLAGS.values())},
    )
    binary = SCRIPT.parents[1] / "src/inferencepilot/fakes/fake_bin/vllm"
    args = argparse.Namespace(
        db=str(tmp_path / "existing.db"),
        port=18000,
        model="openai/gpt-oss-120b",
        binary=str(binary),
        hours=1,
        prompts=2,
        resume=None,
        startup_log=None,
    )
    assert module.run(args) == 0
    store = Store(args.db)
    identity = store.rows("experiments")[0]["id"]
    records = store.records(identity)
    assert len(records["launches"]) == 1
    assert len(records["reps"]) == 30
    assert len(records["points"]) == 6
    assert records["experiment"]["status"] == "completed"
    assert json.loads((tmp_path / "reports/report.json").read_text())["limits"][0].startswith(
        "Existing server"
    )
    args.resume = identity
    store.close()
    assert module.run(args) == 0
    store = Store(args.db)
    assert len(store.records(identity)["reps"]) == 30
    store.close()
