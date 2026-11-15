from __future__ import annotations

import sqlite3

import pytest

from rakho import Rakho


@pytest.fixture
def db(tmp_path):
    store = Rakho(tmp_path / "limits.db")
    yield store
    store.close()


def test_checkpoint_completed_when_idle(db: Rakho):
    db.keep("order is late", actor_id="krishy")
    result = db.forget(actor_id="krishy")
    assert result.checkpoint_requested is True
    assert result.checkpoint_busy == 0
    assert result.checkpoint_completed is True
    assert db.recall("order", actor_id="krishy") == []


def test_checkpoint_reports_busy_with_open_reader(tmp_path):
    path = tmp_path / "busy.db"
    db = Rakho(path)
    db.keep("order is late", actor_id="krishy")
    reader = sqlite3.connect(str(path))
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM memories").fetchone()
        result = db.forget(actor_id="krishy")
        assert result.checkpoint_requested is True
        assert result.checkpoint_completed is False
        assert result.checkpoint_busy == 1
    finally:
        reader.execute("COMMIT")
        reader.close()
        db.close()
