from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from rakho.store import Rakho

ToolFn = Callable[..., str]


def bind_tools(store: Rakho) -> dict[str, ToolFn]:
    """Keep / recall / forget / audit as callables. MCP and tests share these."""

    def keep(content: str, actor_id: str, scope: str = "default") -> str:
        result = store.keep(content, actor_id=actor_id, scope=scope)
        if result.stored:
            return json.dumps({"action": result.action, "content": result.stored.content})
        refused = result.refused
        return json.dumps(
            {
                "action": "skip",
                "reason": refused.reason if refused else "blocked",
                "preview": refused.preview if refused else "",
            }
        )

    def recall(query: str, actor_id: str, scope: str = "default", k: int = 8) -> str:
        hits = store.recall(query, actor_id=actor_id, scope=scope, k=k)
        return json.dumps([{"content": m.content, "score": m.score} for m in hits])

    def forget(actor_id: str, scope: str | None = None) -> str:
        result = store.forget(actor_id=actor_id, scope=scope)
        return json.dumps(
            {
                "memories_deleted": result.memories_deleted,
                "refusals_deleted": result.refusals_deleted,
            }
        )

    def audit(actor_id: str, scope: str | None = None) -> str:
        return json.dumps(
            store.audit(actor_id=actor_id, scope=scope).to_public_dict(),
            ensure_ascii=False,
        )

    return {
        "keep": keep,
        "rakho": keep,
        "recall": recall,
        "nikaalo": recall,
        "forget": forget,
        "bhoolo": forget,
        "audit": audit,
        "dekho": audit,
    }


def _db(*, path: str | None = None, embedder: str | None = None, gate: str | None = None) -> Rakho:
    return Rakho(
        path or os.environ.get("RAKHO_DB", "rakho.db"),
        embedder=embedder or os.environ.get("RAKHO_EMBEDDER", "auto"),
        gate=gate or os.environ.get("RAKHO_GATE", "default"),
    )


def create_mcp(store: Rakho) -> Any:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("rakho")
    tools = bind_tools(store)
    mcp.tool(name="keep", description="Store a memory after the safety gate.")(tools["keep"])
    mcp.tool(name="rakho", description="Hindi: keep a memory.")(tools["rakho"])
    mcp.tool(name="recall", description="Recall memories for this actor.")(tools["recall"])
    mcp.tool(name="nikaalo", description="Hindi: recall memories.")(tools["nikaalo"])
    mcp.tool(name="forget", description="Delete this actor's memories.")(tools["forget"])
    mcp.tool(name="bhoolo", description="Hindi: forget an actor.")(tools["bhoolo"])
    mcp.tool(name="audit", description="Show stored and refused memories.")(tools["audit"])
    mcp.tool(name="dekho", description="Hindi: audit memories.")(tools["dekho"])
    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rakho-mcp", description="Rakho as an MCP memory tool")
    parser.add_argument("--db", default=None)
    parser.add_argument("--embedder", default=None)
    parser.add_argument(
        "--gate",
        default=None,
        help="default, or sluice if sluice-taint is installed",
    )
    args = parser.parse_args(argv)
    if args.db:
        os.environ["RAKHO_DB"] = args.db
    if args.embedder:
        os.environ["RAKHO_EMBEDDER"] = args.embedder
    if args.gate:
        os.environ["RAKHO_GATE"] = args.gate

    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
    except ImportError:
        print("MCP extra missing. pip install 'rakho[mcp]'", file=sys.stderr)
        return 1

    try:
        store = _db(path=args.db, embedder=args.embedder, gate=args.gate)
    except (ImportError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    mcp = create_mcp(store)
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
