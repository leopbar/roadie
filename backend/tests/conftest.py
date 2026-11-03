from __future__ import annotations

from pathlib import Path

import pytest

from roadie.config import REPO_ROOT
from roadie.ingest.csv_loader import Dataset, load_dataset
from roadie.ingest.policy_pdf import ClauseDraft, find_policy_pdf, load_policy_clauses


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return REPO_ROOT / "data"


@pytest.fixture(scope="session")
def dataset(data_dir: Path) -> Dataset:
    return load_dataset(data_dir)


@pytest.fixture(scope="session")
def clauses(data_dir: Path) -> list[ClauseDraft]:
    return load_policy_clauses(find_policy_pdf(data_dir))


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine_at_end():
    from roadie.db.engine import dispose_engine

    yield
    await dispose_engine()
