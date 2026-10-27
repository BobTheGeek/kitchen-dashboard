from datetime import datetime

import pytest

from app import clock
from app.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


@pytest.fixture
def con(store):
    c = store.connect()
    yield c
    c.close()


@pytest.fixture
def freeze(monkeypatch):
    """freeze("2026-10-26T15:20") pins clock.now() to that Chicago wall time."""
    def _freeze(local_iso: str) -> datetime:
        dt = datetime.fromisoformat(local_iso).replace(tzinfo=clock.TZ)
        monkeypatch.setattr(clock, "now", lambda: dt)
        return dt
    return _freeze
