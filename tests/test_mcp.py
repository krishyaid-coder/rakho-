from __future__ import annotations

import json

import pytest

from rakho import Rakho
from rakho.mcp_server import bind_tools


@pytest.fixture
def tools(tmp_path):
    db = Rakho(tmp_path / "mcp.db")
    yield bind_tools(db)
    db.close()


def test_mcp_tools_keep_recall_forget_audit(tools):
    kept = json.loads(tools["keep"]("order is late", "krishy"))
    assert kept["action"] == "store"
    assert "late" in kept["content"]

    skipped = json.loads(tools["rakho"]("password is hunter2", "krishy"))
    assert skipped["action"] == "skip"
    assert "hunter2" not in skipped.get("preview", "")

    hits = json.loads(tools["nikaalo"]("order", "krishy"))
    assert hits
    assert all("hunter2" not in h["content"] for h in hits)

    report = json.loads(tools["dekho"]("krishy"))
    assert report["stored_count"] >= 1
    assert report["refused_count"] >= 1

    forgotten = json.loads(tools["bhoolo"]("krishy"))
    assert forgotten["memories_deleted"] >= 1
    empty = json.loads(tools["audit"]("krishy"))
    assert empty["stored_count"] == 0
    assert empty["refused_count"] == 0


def test_mcp_tool_names(tmp_path):
    db = Rakho(tmp_path / "names.db")
    try:
        names = set(bind_tools(db))
    finally:
        db.close()
    assert names == {
        "keep",
        "rakho",
        "recall",
        "nikaalo",
        "forget",
        "bhoolo",
        "audit",
        "dekho",
    }
