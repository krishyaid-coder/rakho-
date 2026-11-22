from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from rakho.embeddings import Embedder, resolve_embedder
from rakho.gate import AllowAllGate, DefaultPolicyGate, PolicyGate, is_injection, mask_preview
from rakho.languages import ACTIONS, BUILT_IN, invert, normalize_pack
from rakho.graph import build_ascii, build_mermaid, forgotten_ids_from
from rakho.models import (
    AuditReport,
    Decision,
    ForgetResult,
    GraphReport,
    KeepResult,
    Memory,
    Mutation,
    RecallResult,
    Refusal,
)
from rakho.storage import SQLiteEngine, StorageEngine, value_fingerprint


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def pack_to_budget(memories: list[Memory], budget: int) -> list[Memory]:
    if budget <= 0:
        return []
    out: list[Memory] = []
    used = 0
    for mem in memories:
        cost = estimate_tokens(mem.content)
        if out and used + cost > budget:
            break
        out.append(mem)
        used += cost
        if used >= budget:
            break
    return out


class Rakho:
    """Embeddable agent memory. Canonical API: keep, recall, forget, audit."""

    def __init__(
        self,
        path: str | Path = "rakho.db",
        *,
        gate: PolicyGate | str | None = None,
        embedder: Embedder | str | None = None,
        storage: StorageEngine | None = None,
        allow_all: bool = False,
    ) -> None:
        self.gate: PolicyGate = coerce_gate(gate, allow_all=allow_all)
        self.embedder = resolve_embedder(embedder)
        self.storage = storage or SQLiteEngine(path)
        self._seed_languages()
        self._verbs = self._load_verbs()

    def _seed_languages(self) -> None:
        for language, mapping in BUILT_IN.items():
            self.storage.add_verbs(language, mapping)

    def _load_verbs(self) -> dict[str, str]:
        stored = self.storage.all_verbs()
        if stored:
            return stored
        return invert(BUILT_IN)

    def keep(
        self,
        content: str,
        *,
        actor_id: str,
        scope: str = "default",
        source: str | None = None,
        session_id: str | None = None,
        origin_tool: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KeepResult:
        actor_id = _require_actor(actor_id)
        context = {
            "actor_id": actor_id,
            "scope": scope,
            "source": source,
            "session_id": session_id,
            "origin_tool": origin_tool,
            "metadata": metadata or {},
        }
        decision = self.gate.inspect(content, context)
        fp = value_fingerprint(content)
        if self.storage.has_tombstone(actor_id=actor_id, fingerprint=fp):
            decision = Decision(
                action="skip",
                content="",
                reason="tombstone",
                labels=list(decision.labels) or ["tombstone"],
            )

        if decision.action == "skip":
            refusal = Refusal(
                actor_id=actor_id,
                scope=scope,
                reason=decision.reason,
                labels=list(decision.labels),
                preview=mask_preview(content, decision),
            )
            self.storage.put_refusal(refusal)
            self.storage.put_tombstone(
                actor_id=actor_id,
                fingerprint=fp,
                reason=decision.reason,
                labels=list(decision.labels),
            )
            self.storage.put_mutation(
                Mutation(
                    op="skip",
                    actor_id=actor_id,
                    scope=scope,
                    target_id=refusal.id,
                    detail={"reason": decision.reason, "labels": list(decision.labels)},
                )
            )
            return KeepResult(action="skip", refused=refusal)

        memory = Memory(
            content=decision.content,
            actor_id=actor_id,
            scope=scope,
            source=source,
            session_id=session_id,
            origin_tool=origin_tool,
            sensitivity=decision.sensitivity,
            metadata=metadata or {},
            embedding=self.embedder.embed(decision.content, role="document"),
            embedder=getattr(self.embedder, "name", None),
        )
        self.storage.put(memory)
        self.storage.put_mutation(
            Mutation(
                op="redact" if decision.action == "redact" else "keep",
                actor_id=actor_id,
                scope=scope,
                target_id=memory.id,
                detail={"labels": list(decision.labels), "embedder": memory.embedder},
            )
        )
        return KeepResult(action=decision.action, stored=memory)

    def recall(
        self,
        query: str,
        *,
        actor_id: str,
        scope: str = "default",
        k: int = 8,
        budget: int = 512,
        cursor: str | None = None,
    ) -> RecallResult:
        actor_id = _require_actor(actor_id)
        if is_injection(query):
            return RecallResult([], packed_tokens=0, budget=budget, skipped=0)
        seen: list[str] = []
        if cursor:
            page = _decode_cursor(cursor)
            if page["qh"] != _query_key(query):
                raise ValueError("cursor is for a different query")
            if page["actor"] != actor_id:
                raise ValueError("cursor is for a different actor")
            if page["scope"] != scope:
                raise ValueError("cursor is for a different scope")
            seen = list(page["seen"])
        query_vec = self.embedder.embed(query, role="query") if query.strip() else None
        hits = self.storage.search(
            query,
            query_vec,
            actor_id=actor_id,
            scope=scope,
            k=max(k, 1),
            query_embedder=getattr(self.embedder, "name", None),
            query_dim=len(query_vec) if query_vec is not None else None,
        )
        if seen:
            skip = set(seen)
            hits = [m for m in hits if m.id not in skip]
        packed = pack_to_budget(hits, budget)
        packed_tokens = sum(estimate_tokens(m.content) for m in packed)
        skipped = max(0, len(hits) - len(packed))
        next_seen = seen + [m.id for m in packed]
        next_cursor = None
        if skipped:
            next_cursor = _encode_cursor(
                query=query, actor_id=actor_id, scope=scope, seen=next_seen
            )
        if packed:
            self.storage.touch(m.id for m in packed)
        packed_ids = {m.id for m in packed}
        held_back = [m for m in hits if m.id not in packed_ids]
        return RecallResult(
            packed,
            packed_tokens=packed_tokens,
            budget=budget,
            skipped=skipped,
            cursor=next_cursor,
            held_back=held_back,
        )

    def forget(
        self,
        *,
        actor_id: str | None = None,
        scope: str | None = None,
        session_id: str | None = None,
        id: str | None = None,
    ) -> ForgetResult:
        if not any([actor_id, session_id, id]):
            raise ValueError(
                "forget() needs actor_id, session_id, or id — refusing to wipe the whole store"
            )
        memories_deleted, refusals_deleted, orphaned, deleted_ids = self.storage.delete(
            actor_id=actor_id,
            scope=scope,
            session_id=session_id,
            id=id,
        )
        log_actor = actor_id or "unknown"
        if orphaned:
            for target in orphaned:
                self.storage.put_mutation(
                    Mutation(
                        op="orphan",
                        actor_id=log_actor,
                        scope=scope,
                        target_id=target,
                        detail={"reason": "source_forgotten"},
                    )
                )
        self.storage.put_mutation(
            Mutation(
                op="forget",
                actor_id=log_actor,
                scope=scope,
                detail={
                    "memories_deleted": memories_deleted,
                    "memories_orphaned": len(orphaned),
                    "deleted_ids": deleted_ids,
                    "filter": {"actor_id": actor_id, "session_id": session_id, "id": id},
                },
            )
        )
        return ForgetResult(
            memories_deleted=memories_deleted,
            refusals_deleted=refusals_deleted,
            memories_orphaned=len(orphaned),
        )

    def audit(self, *, actor_id: str, scope: str | None = None) -> AuditReport:
        actor_id = _require_actor(actor_id)
        return AuditReport(
            actor_id=actor_id,
            scope=scope,
            memories=self.storage.list_memories(actor_id=actor_id, scope=scope),
            refusals=self.storage.list_refusals(actor_id=actor_id, scope=scope),
            mutations=self.storage.list_mutations(actor_id=actor_id, scope=scope),
        )

    def graph(
        self,
        query: str = "",
        *,
        actor_id: str,
        scope: str = "default",
        k: int = 8,
        budget: int = 512,
    ) -> GraphReport:
        """Picture of this actor's notebook: bag, door, orphans, forget receipts."""
        actor_id = _require_actor(actor_id)
        report = self.audit(actor_id=actor_id, scope=scope)
        packed: list[Memory] = []
        skipped: list[Memory] = []
        unranked: list[Memory] = []
        packed_tokens = 0
        used_budget = budget
        if query.strip():
            page = self.recall(query, actor_id=actor_id, scope=scope, k=k, budget=budget)
            packed = list(page)
            skipped = list(page.held_back)
            packed_tokens = page.packed_tokens
            used_budget = page.budget
            shown = {m.id for m in packed} | {m.id for m in skipped}
            unranked = [
                m
                for m in report.memories
                if m.trust != "orphaned" and m.id not in shown
            ]
        else:
            packed = [m for m in report.memories if m.trust != "orphaned"]
        orphaned = [m for m in report.memories if m.trust == "orphaned"]
        forgotten = forgotten_ids_from(report.mutations)
        payload = dict(
            actor_id=actor_id,
            query=query,
            packed=packed,
            skipped=skipped,
            unranked=unranked,
            refused=report.refusals,
            orphaned=orphaned,
            forgotten_ids=forgotten,
            packed_tokens=packed_tokens,
            budget=used_budget,
        )
        return GraphReport(
            actor_id=actor_id,
            query=query,
            mermaid=build_mermaid(**payload),
            ascii=build_ascii(**payload),
            packed=packed,
            skipped=skipped,
            unranked=unranked,
            refused=list(report.refusals),
            orphaned=orphaned,
            forgotten_ids=forgotten,
            packed_tokens=packed_tokens,
            budget=used_budget,
            scope=scope,
        )

    def learn(self, language: str, verbs: dict[str, str | list[str]]) -> dict[str, str]:
        language = language.strip()
        if not language:
            raise ValueError("language name is required")
        pack = normalize_pack(verbs)
        self.storage.add_verbs(language, pack)
        self._verbs = self._load_verbs()
        return {action: pack[action][0] for action in ACTIONS}

    def resolve(self, word: str) -> str:
        action = self._verbs.get(word.strip().casefold())
        if action is None:
            known = ", ".join(sorted(self._verbs))
            raise ValueError(f"unknown command '{word}'. known verbs: {known}")
        return action

    def close(self) -> None:
        close = getattr(self.storage, "close", None)
        if close:
            close()

    def __enter__(self) -> Rakho:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            action = self.resolve(name)
        except ValueError as exc:
            raise AttributeError(name) from exc
        return getattr(self, action)

    # Documented aliases so they show up on the class.
    def store(self, *args: Any, **kwargs: Any) -> KeepResult:
        return self.keep(*args, **kwargs)

    def rakho(self, *args: Any, **kwargs: Any) -> KeepResult:
        return self.keep(*args, **kwargs)

    def nikaalo(self, *args: Any, **kwargs: Any) -> RecallResult:
        return self.recall(*args, **kwargs)

    def bhoolo(self, **kwargs: Any) -> ForgetResult:
        return self.forget(**kwargs)

    def dekho(self, *args: Any, **kwargs: Any) -> AuditReport | GraphReport:
        if args or "query" in kwargs or kwargs.get("graph"):
            kwargs.pop("graph", None)
            return self.graph(*args, **kwargs)
        return self.audit(**kwargs)


def coerce_gate(gate: PolicyGate | str | None, *, allow_all: bool = False) -> PolicyGate:
    if isinstance(gate, PolicyGate):
        return gate
    if isinstance(gate, str):
        key = gate.strip().lower()
        if key in ("", "default"):
            return AllowAllGate() if allow_all else DefaultPolicyGate()
        if key == "sluice":
            from rakho.sluice_gate import SluiceGate

            return SluiceGate()
        raise ValueError(f"unknown gate {gate!r}. use 'default' or 'sluice'")
    if gate is None:
        return AllowAllGate() if allow_all else DefaultPolicyGate()
    raise TypeError(f"gate must be a PolicyGate, str, or None, not {type(gate).__name__}")


def _query_key(query: str) -> str:
    return hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:16]


def _encode_cursor(*, query: str, actor_id: str, scope: str, seen: list[str]) -> str:
    payload = {
        "v": 1,
        "qh": _query_key(query),
        "actor": actor_id,
        "scope": scope,
        "seen": seen,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    pad = "=" * ((4 - len(cursor) % 4) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + pad))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("bad recall cursor") from exc
    if data.get("v") != 1 or not isinstance(data.get("seen"), list):
        raise ValueError("bad recall cursor")
    return data


def _require_actor(actor_id: str) -> str:
    if not actor_id or not str(actor_id).strip():
        raise ValueError("actor_id is required")
    return str(actor_id).strip()
