from pathlib import Path

import pytest
import yaml


@pytest.fixture
def example():
    path = Path(__file__).resolve().parents[1] / "configs/experiment_qwen3_8b.yaml"
    return yaml.safe_load(path.read_text())
