from __future__ import annotations

import argparse
import json
import os
import sys

from rakho.store import Rakho


def _db() -> Rakho:
    path = os.environ.get("RAKHO_DB", "rakho.db")
    embedder = os.environ.get("RAKHO_EMBEDDER", "auto")
    gate = None
    if os.environ.get("RAKHO_GATE", "").strip().lower() == "sluice":
        from rakho.sluice_gate import SluiceGate

        gate = SluiceGate()
    return Rakho(path, embedder=embedder, gate=gate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rakho-mcp", description="Rakho as an MCP memory tool")
    parser.add_argument("--db", default=None)
    parser.add_argument("--embedder", default=None)
    args = parser.parse_args(argv)
    if args.db:
        os.environ["RAKHO_DB"] = args.db
    if args.embedder:
        os.environ["RAKHO_EMBEDDER"] = args.embedder

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("MCP extra missing. pip install 'rakho[mcp]'", file=sys.stderr)
        return 1

    mcp = FastMCP("rakho")
    store = _db()

    def _keep(content: str, actor_id: str, scope: str = "default") -> str:
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

    def _recall(query: str, actor_id: str, scope: str = "default", k: int = 8) -> str:
        hits = store.recall(query, actor_id=actor_id, scope=scope, k=k)
        return json.dumps([{"content": m.content, "score": m.score} for m in hits])

    def _forget(actor_id: str, scope: str | None = None) -> str:
        result = store.forget(actor_id=actor_id, scope=scope)
        return json.dumps(
            {
                "memories_deleted": result.memories_deleted,
                "refusals_deleted": result.refusals_deleted,
            }
        )

    def _audit(actor_id: str, scope: str | None = None) -> str:
        return json.dumps(
            store.audit(actor_id=actor_id, scope=scope).to_public_dict(),
            ensure_ascii=False,
        )

    mcp.tool(name="keep", description="Store a memory after the safety gate.")(_keep)
    mcp.tool(name="rakho", description="Hindi: keep a memory.")(_keep)
    mcp.tool(name="recall", description="Recall memories for this actor.")(_recall)
    mcp.tool(name="nikaalo", description="Hindi: recall memories.")(_recall)
    mcp.tool(name="forget", description="Delete this actor's memories.")(_forget)
    mcp.tool(name="bhoolo", description="Hindi: forget an actor.")(_forget)
    mcp.tool(name="audit", description="Show stored and refused memories.")(_audit)
    mcp.tool(name="dekho", description="Hindi: audit memories.")(_audit)

    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
