from __future__ import annotations

import pytest

from rakho import Rakho
from rakho.cli import main


@pytest.fixture
def db(tmp_path):
    store = Rakho(tmp_path / "graph.db")
    yield store
    store.close()


def test_graph_is_one_actor_and_shows_scores(db: Rakho):
    db.keep("vendor invoice 4000 USD", actor_id="krishy")
    db.keep("priya prefers email followups", actor_id="priya")
    picture = db.graph("invoice", actor_id="krishy")
    assert "krishy" in picture.mermaid
    assert "invoice" in picture.mermaid
    assert "vec " in picture.mermaid
    assert "priya" not in picture.mermaid.lower()
    assert "email followups" not in picture.mermaid
    assert "packed" in picture.ascii
    assert "query" in picture.ascii
    assert "priya" not in picture.ascii.lower()
    assert picture.packed
    assert all(m.actor_id == "krishy" for m in picture.packed)


def test_graph_marks_skipped_when_bag_is_tiny(db: Rakho):
    db.keep("word " * 40 + "invoice-one", actor_id="krishy")
    db.keep("word " * 40 + "invoice-two", actor_id="krishy")
    picture = db.graph("word", actor_id="krishy", budget=1)
    assert picture.skipped
    assert "skipped" in picture.mermaid
    assert "bag full" in picture.mermaid
    assert "skipped" in picture.ascii
    assert "bag full" in picture.ascii
    assert "skipped 1" in picture.ascii or f"skipped {len(picture.skipped)}" in picture.ascii


def test_graph_shows_orphaned_and_forgotten_id(db: Rakho):
    source = db.keep("order is late", actor_id="krishy")
    assert source.stored is not None
    derived = db.keep(
        "customer still waiting",
        actor_id="krishy",
        metadata={"derived_from": [source.stored.id]},
    )
    assert derived.stored is not None
    db.forget(actor_id="krishy", id=source.stored.id)
    picture = db.graph("waiting", actor_id="krishy")
    assert picture.orphaned
    assert "orphaned" in picture.mermaid
    assert source.stored.id in picture.forgotten_ids
    assert "forgotten" in picture.mermaid
    assert "removed" in picture.mermaid
    assert "orphaned" in picture.ascii
    assert "forgotten" in picture.ascii


def test_graph_shows_bag_unranked_and_refused(db: Rakho):
    db.keep("vendor invoice 4000 USD", actor_id="krishy")
    db.keep("zebra pancakes with maple", actor_id="krishy")
    db.keep("password is hunter2", actor_id="krishy")
    db.keep("priya prefers email followups", actor_id="priya")
    picture = db.graph("invoice", actor_id="krishy")
    assert "packed " in picture.ascii and "/512" in picture.ascii
    assert "skipped 0" in picture.ascii
    assert picture.unranked
    assert any("pancakes" in m.content for m in picture.unranked)
    assert "didn't rank" in picture.ascii
    assert "pancakes" in picture.ascii
    assert picture.refused
    assert "refused" in picture.ascii
    assert "hunter2" not in picture.ascii
    assert "hunter2" not in picture.mermaid
    assert "priya" not in picture.ascii.lower()
    assert "email followups" not in picture.ascii
    public = picture.to_public_dict()
    assert public["packed_tokens"] > 0
    assert public["budget"] == 512


def test_cli_graph(tmp_path, capsys):
    path = str(tmp_path / "cli.db")
    assert main(["--db", path, "keep", "--actor", "krishy", "order is late"]) == 0
    capsys.readouterr()
    assert main(["--db", path, "dekho", "--actor", "krishy", "--graph", "order"]) == 0
    out = capsys.readouterr().out
    assert "notebook krishy" in out
    assert "query" in out
    assert "packed" in out
    assert "flowchart" not in out
    assert main(["--db", path, "dekho", "--actor", "krishy", "--graph", "--mermaid", "order"]) == 0
    mermaid = capsys.readouterr().out
    assert "flowchart" in mermaid
    assert "krishy" in mermaid
