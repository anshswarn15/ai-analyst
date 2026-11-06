from pathlib import Path

import pytest

from app.config import Settings
from app.core.session import SessionStore

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


@pytest.fixture
def settings():
    return Settings.from_env()


@pytest.fixture
def session(settings):
    s = SessionStore(settings).create()
    for p in sorted(SAMPLE_DIR.glob("*.csv")):
        s.add_csv(p.name, p.read_bytes())
    return s
