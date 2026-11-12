from pathlib import Path

import pytest

from collection_plan.config import load_config
from collection_plan.pipeline import run_plan
from collection_plan.synthetic import generate_history

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def cfg():
    return load_config(ROOT / "config" / "assumptions.yaml")


@pytest.fixture(scope="session")
def history():
    return generate_history(year=2026, last_actual_month=10, seed=42)


@pytest.fixture(scope="session")
def result(history, cfg):
    return run_plan(history, cfg)
