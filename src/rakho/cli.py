from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from rakho.banner import print_banner
from rakho.store import Rakho


class _Parser(argparse.ArgumentParser):
    def print_help(self, file=None) -> None:
        print_banner(hints=False)
        super().print_help(file)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="rakho",
        description="Agent memory that inspects before it keeps.",
    )
    parser.add_argument("--db", default="rakho.db", help="SQLite file (default: rakho.db)")
    parser.add_argument(
        "verb",
        nargs="?",
        default=None,
        help="keep/recall/forget/audit, rakho/nikaalo/bhoolo/dekho, learn, or init",
    )
    parser.add_argument("rest", nargs="*", help="content, query, or language name")
    parser.add_argument("--actor", help="actor_id (required except learn)")
    parser.add_argument("--scope", default=None, help="namespace (default: default for keep/recall)")
    parser.add_argument("--session", dest="session_id")
    parser.add_argument("--source")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--budget", type=int, default=512)
    parser.add_argument("--id", dest="memory_id", help="memory id for forget")
    parser.add_argument("--keep", dest="v_keep", help="learn: keep verb")
    parser.add_argument("--recall", dest="v_recall", help="learn: recall verb")
    parser.add_argument("--forget", dest="v_forget", help="learn: forget verb")
    parser.add_argument("--audit", dest="v_audit", help="learn: audit verb")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument(
        "--embedder",
        default="hash",
        help="hash (offline default), auto, jina, or hf",
    )
    parser.add_argument(
        "--gate",
        default="default",
        help="default, or sluice if sluice-taint is installed",
    )
    return parser


def _open(args: argparse.Namespace) -> Rakho:
    try:
        return Rakho(args.db, embedder=args.embedder, gate=args.gate)
    except (ImportError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    verb = (args.verb or "").strip().casefold()
    if not verb or verb in {"init", "welcome"}:
        print_banner()
        if verb == "init":
            try:
                db = _open(args)
            except SystemExit as exc:
                return int(exc.code or 2)
            db.close()
            gate = args.gate.strip().lower()
            extra = " · sluice on" if gate == "sluice" else ""
            print(f"  notebook ready · {args.db}{extra}\n")
        return 0
    try:
        db = _open(args)
    except SystemExit as exc:
        return int(exc.code or 2)
    try:
        return _dispatch(db, args)
    finally:
        db.close()


def _dispatch(db: Rakho, args: argparse.Namespace) -> int:
    verb = args.verb.strip().casefold()
    if verb == "learn":
        return _learn(db, args)

    action = db.resolve(verb)

    if action in {"keep", "recall", "audit"} and not args.actor:
        print("error: --actor is required", file=sys.stderr)
        return 2

    if action == "keep":
        content = " ".join(args.rest).strip()
        if not content:
            print("error: keep needs content", file=sys.stderr)
            return 2
        result = db.keep(
            content,
            actor_id=args.actor,
            scope=args.scope or "default",
            source=args.source,
            session_id=args.session_id,
        )
        return _print_keep(result, as_json=args.json)

    if action == "recall":
        query = " ".join(args.rest).strip()
        hits = db.recall(
            query,
            actor_id=args.actor,
            scope=args.scope or "default",
            k=args.k,
            budget=args.budget,
        )
        return _print_recall(hits, as_json=args.json)

    if action == "forget":
        if not args.actor and not args.memory_id and not args.session_id:
            print("error: forget needs --actor, --session, or --id", file=sys.stderr)
            return 2
        result = db.forget(
            actor_id=args.actor,
            scope=args.scope,
            session_id=args.session_id,
            id=args.memory_id,
        )
        payload = {
            "memories_deleted": result.memories_deleted,
            "refusals_deleted": result.refusals_deleted,
        }
        print(json.dumps(payload) if args.json else f"forgot {result.deleted} rows")
        return 0

    if action == "audit":
        report = db.audit(actor_id=args.actor, scope=args.scope)
        if args.json:
            print(json.dumps(report.to_public_dict(), indent=2, ensure_ascii=False))
            return 0
        print(f"stored {len(report.memories)}  refused {len(report.refusals)}")
        for mem in report.memories:
            dim = len(mem.embedding) if mem.embedding else 0
            print(f"  keep  {mem.sensitivity:8}  {dim:>4}d  {mem.content}")
        for ref in report.refusals:
            print(f"  skip  {ref.reason:8}  {ref.preview}")
        return 0

    print(f"error: unhandled action {action}", file=sys.stderr)
    return 2


def _learn(db: Rakho, args: argparse.Namespace) -> int:
    language = args.rest[0] if args.rest else ""
    pack = {
        "keep": args.v_keep,
        "recall": args.v_recall,
        "forget": args.v_forget,
        "audit": args.v_audit,
    }
    if not language or any(v is None for v in pack.values()):
        print(
            "usage: rakho learn <language> --keep WORD --recall WORD --forget WORD --audit WORD",
            file=sys.stderr,
        )
        return 2
    learned = db.learn(language, pack)  # type: ignore[arg-type]
    print(json.dumps({"language": language, "verbs": learned}, ensure_ascii=False))
    return 0


def _print_keep(result: Any, *, as_json: bool) -> int:
    if as_json:
        payload: dict[str, Any] = {"action": result.action}
        if result.stored:
            payload["stored"] = result.stored.to_public_dict()
        if result.refused:
            payload["refused"] = result.refused.to_public_dict()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if result.stored:
        print(f"{result.action}: {result.stored.content}")
    elif result.refused:
        print(f"skip: {result.refused.reason} {result.refused.preview}")
    return 0


def _print_recall(hits: list[Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps([m.to_public_dict() for m in hits], indent=2, ensure_ascii=False))
        return 0
    if not hits:
        print("(nothing)")
        return 0
    for mem in hits:
        print(f"{mem.score:.3f}  {mem.content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
