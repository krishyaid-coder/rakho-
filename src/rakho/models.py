from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


Action = Literal["store", "redact", "skip"]
Sensitivity = Literal["clean", "redacted"]
Kind = Literal["episode"]
Trust = Literal["trusted", "orphaned"]
MutationOp = Literal["keep", "redact", "skip", "forget", "orphan"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


@dataclass
class Decision:
    action: Action
    content: str
    reason: str = ""
    labels: list[str] = field(default_factory=list)

    @property
    def sensitivity(self) -> Sensitivity:
        return "redacted" if self.action == "redact" else "clean"


@dataclass
class Memory:
    content: str
    actor_id: str
    id: str = field(default_factory=new_id)
    embedding: list[float] | None = None
    kind: Kind = "episode"
    source: str | None = None
    session_id: str | None = None
    origin_tool: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    last_used_at: datetime = field(default_factory=utcnow)
    sensitivity: Sensitivity = "clean"
    scope: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    vec_score: float = 0.0
    fts_score: float = 0.0
    recency_score: float = 0.0
    embedder: str | None = None
    trust: Trust = "trusted"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "kind": self.kind,
            "actor_id": self.actor_id,
            "scope": self.scope,
            "source": self.source,
            "session_id": self.session_id,
            "origin_tool": self.origin_tool,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "sensitivity": self.sensitivity,
            "metadata": self.metadata,
            "score": self.score,
            "vec_score": self.vec_score,
            "fts_score": self.fts_score,
            "recency_score": self.recency_score,
            "embedding_dim": len(self.embedding) if self.embedding else 0,
            "embedder": self.embedder,
            "trust": self.trust,
        }


@dataclass
class Refusal:
    actor_id: str
    reason: str
    preview: str
    id: str = field(default_factory=new_id)
    scope: str = "default"
    labels: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "scope": self.scope,
            "reason": self.reason,
            "labels": self.labels,
            "preview": self.preview,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Mutation:
    op: MutationOp
    actor_id: str
    id: str = field(default_factory=new_id)
    scope: str | None = None
    target_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "actor_id": self.actor_id,
            "scope": self.scope,
            "target_id": self.target_id,
            "detail": self.detail,
            "created_at": self.created_at.isoformat(),
        }


class RecallResult(list):
    """Ranked notes that fit the token bag, plus the truth about what did not.

    Still a list, so `for m in db.nikaalo(...)` and `== []` keep working.
    """

    packed_tokens: int
    budget: int
    skipped: int
    cursor: str | None
    held_back: list[Memory]

    def __init__(
        self,
        memories: list[Memory] | None = None,
        *,
        packed_tokens: int = 0,
        budget: int = 0,
        skipped: int = 0,
        cursor: str | None = None,
        held_back: list[Memory] | None = None,
    ) -> None:
        super().__init__(memories or [])
        self.packed_tokens = packed_tokens
        self.budget = budget
        self.skipped = skipped
        self.cursor = cursor
        self.held_back = held_back or []

    @property
    def more(self) -> bool:
        return bool(self.cursor)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "memories": [m.to_public_dict() for m in self],
            "packed_tokens": self.packed_tokens,
            "budget": self.budget,
            "skipped": self.skipped,
            "cursor": self.cursor,
            "more": self.more,
            "held_back": [m.to_public_dict() for m in self.held_back],
        }


@dataclass
class KeepResult:
    action: Action
    stored: Memory | None = None
    refused: Refusal | None = None

    @property
    def kept(self) -> bool:
        return self.stored is not None


@dataclass
class ForgetResult:
    memories_deleted: int
    refusals_deleted: int = 0
    memories_orphaned: int = 0

    @property
    def deleted(self) -> int:
        return self.memories_deleted + self.refusals_deleted


@dataclass
class GraphReport:
    """One actor, one look at how recall ranked and what left the box."""

    actor_id: str
    query: str
    mermaid: str
    ascii: str = ""
    packed: list[Memory] = field(default_factory=list)
    skipped: list[Memory] = field(default_factory=list)
    unranked: list[Memory] = field(default_factory=list)
    refused: list[Refusal] = field(default_factory=list)
    orphaned: list[Memory] = field(default_factory=list)
    forgotten_ids: list[str] = field(default_factory=list)
    packed_tokens: int = 0
    budget: int = 512
    scope: str = "default"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "scope": self.scope,
            "query": self.query,
            "mermaid": self.mermaid,
            "ascii": self.ascii,
            "packed": [m.to_public_dict() for m in self.packed],
            "skipped": [m.to_public_dict() for m in self.skipped],
            "unranked": [m.to_public_dict() for m in self.unranked],
            "refused": [r.to_public_dict() for r in self.refused],
            "orphaned": [m.to_public_dict() for m in self.orphaned],
            "forgotten_ids": self.forgotten_ids,
            "packed_tokens": self.packed_tokens,
            "budget": self.budget,
        }


@dataclass
class AuditReport:
    memories: list[Memory]
    refusals: list[Refusal]
    actor_id: str
    scope: str | None = None
    mutations: list[Mutation] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "scope": self.scope,
            "stored": [m.to_public_dict() for m in self.memories],
            "refused": [r.to_public_dict() for r in self.refusals],
            "mutations": [m.to_public_dict() for m in self.mutations],
            "stored_count": len(self.memories),
            "refused_count": len(self.refusals),
            "mutation_count": len(self.mutations),
        }
