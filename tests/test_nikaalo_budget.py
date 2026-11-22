from __future__ import annotations

import pytest

from rakho import Rakho


@pytest.fixture
def db(tmp_path):
    store = Rakho(tmp_path / "budget.db")
    yield store
    store.close()


def _long(tag: str) -> str:
    return f"{tag} " + ("word " * 40).strip()


def test_nikaalo_reports_skipped_and_pages(db: Rakho):
    first = db.keep(_long("vendor-invoice-4000"), actor_id="krishy")
    second = db.keep(_long("order-is-late"), actor_id="krishy")
    third = db.keep(_long("blocked-attacker-payee"), actor_id="krishy")
    assert first.stored and second.stored and third.stored

    page = db.nikaalo("word", actor_id="krishy", k=8, budget=1)
    assert len(page) == 1
    assert page.skipped == 2
    assert page.more is True
    assert page.cursor
    assert page.packed_tokens >= 1
    assert page.budget == 1
    seen = {page[0].id}

    rest = db.nikaalo("word", actor_id="krishy", k=8, budget=1, cursor=page.cursor)
    assert len(rest) == 1
    assert rest[0].id not in seen
    seen.add(rest[0].id)
    assert rest.skipped == 1
    assert rest.cursor

    last = db.nikaalo("word", actor_id="krishy", k=8, budget=1, cursor=rest.cursor)
    assert len(last) == 1
    assert last[0].id not in seen
    assert last.skipped == 0
    assert last.cursor is None
    assert last.more is False


def test_cursor_rejects_a_different_query(db: Rakho):
    db.keep(_long("vendor-invoice-4000"), actor_id="krishy")
    db.keep(_long("order-is-late"), actor_id="krishy")
    page = db.nikaalo("word", actor_id="krishy", budget=1)
    with pytest.raises(ValueError, match="different query"):
        db.nikaalo("late", actor_id="krishy", budget=1, cursor=page.cursor)


def test_list_compat_empty_equals_list(db: Rakho):
    page = db.nikaalo("nothing-here", actor_id="krishy")
    assert page == []
    assert list(page) == []
    assert page.skipped == 0
    assert page.cursor is None
