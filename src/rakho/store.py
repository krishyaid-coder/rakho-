from __future__ import annotations

from pathlib import Path
from typing import Any

from rakho.embeddings import Embedder, resolve_embedder
from rakho.gate import AllowAllGate, DefaultPolicyGate, PolicyGate, mask_preview
from rakho.languages import ACTIONS, BUILT_IN, invert, normalize_pack
from rakho.models import (
    AuditReport,
    ForgetResult,
    KeepResult,
    Memory,
    Refusal,
)
from rakho.storage import SQLiteEngine, StorageEngine


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
        }
        decision = self.gate.inspect(content, context)

        if decision.action == "skip":
            refusal = Refusal(
                actor_id=actor_id,
                scope=scope,
                reason=decision.reason,
                labels=list(decision.labels),
                preview=mask_preview(content, decision),
            )
            self.storage.put_refusal(refusal)
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
        )
        self.storage.put(memory)
        return KeepResult(action=decision.action, stored=memory)

    def recall(
        self,
        query: str,
        *,
        actor_id: str,
        scope: str = "default",
        k: int = 8,
        budget: int = 512,
    ) -> list[Memory]:
        actor_id = _require_actor(actor_id)
        query_vec = self.embedder.embed(query, role="query") if query.strip() else None
        hits = self.storage.search(
            query,
            query_vec,
            actor_id=actor_id,
            scope=scope,
            k=max(k, 1),
        )
        packed = pack_to_budget(hits, budget)
        if packed:
            self.storage.touch(m.id for m in packed)
        return packed

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
        memories_deleted, refusals_deleted = self.storage.delete(
            actor_id=actor_id,
            scope=scope,
            session_id=session_id,
            id=id,
        )
        return ForgetResult(
            memories_deleted=memories_deleted,
            refusals_deleted=refusals_deleted,
        )

    def audit(self, *, actor_id: str, scope: str | None = None) -> AuditReport:
        actor_id = _require_actor(actor_id)
        return AuditReport(
            actor_id=actor_id,
            scope=scope,
            memories=self.storage.list_memories(actor_id=actor_id, scope=scope),
            refusals=self.storage.list_refusals(actor_id=actor_id, scope=scope),
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

    def nikaalo(self, *args: Any, **kwargs: Any) -> list[Memory]:
        return self.recall(*args, **kwargs)

    def bhoolo(self, **kwargs: Any) -> ForgetResult:
        return self.forget(**kwargs)

    def dekho(self, **kwargs: Any) -> AuditReport:
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


def _require_actor(actor_id: str) -> str:
    if not actor_id or not str(actor_id).strip():
        raise ValueError("actor_id is required")
    return str(actor_id).strip()
