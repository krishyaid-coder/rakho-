"""A tiny support agent that uses Rakho as its notebook.

No LLM required. Run:

    python3 examples/agent.py
"""

from __future__ import annotations

from rakho import Rakho


def handle(db: Rakho, actor: str, utterance: str) -> str:
    kept = db.keep(utterance, actor_id=actor, origin_tool="support_agent")
    if kept.action == "skip":
        return f"(gate refused: {kept.refused.reason if kept.refused else 'blocked'})"

    hits = db.recall(utterance, actor_id=actor, k=3)
    notes = "; ".join(h.content for h in hits[:3]) or "nothing yet"
    return f"noted. I remember: {notes}"


def main() -> None:
    db = Rakho("/tmp/rakho-agent.db", embedder="auto")
    print("embedder:", type(db.embedder).__name__)
    print()

    print("Ankit:", "my order is late")
    print("agent:", handle(db, "ankit", "my order is late"))
    print()

    print("Ankit:", "password is hunter2")
    print("agent:", handle(db, "ankit", "password is hunter2"))
    print()

    print("Ankit:", "what's the status of my order?")
    print("agent:", handle(db, "ankit", "what's the status of my order?"))
    print()

    print("Priya:", "I prefer email")
    print("agent:", handle(db, "priya", "I prefer email"))
    print()

    print("forget Ankit…")
    db.forget(actor_id="ankit")
    empty = db.dekho(actor_id="ankit")
    priya = db.dekho(actor_id="priya")
    print("Ankit stored/refused:", len(empty.memories), len(empty.refusals))
    print("Priya still has:", [m.content for m in priya.memories])
    db.close()


if __name__ == "__main__":
    main()
