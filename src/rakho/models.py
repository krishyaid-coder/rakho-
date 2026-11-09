from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


Action = Literal["store", "redact", "skip"]
Sensitivity = Literal["clean", "redacted"]
Kind = Literal["episode"]


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
    refusals_deleted: int

    @property
    def deleted(self) -> int:
        return self.memories_deleted + self.refusals_deleted


@dataclass
class AuditReport:
    memories: list[Memory]
    refusals: list[Refusal]
    actor_id: str
    scope: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "scope": self.scope,
            "stored": [m.to_public_dict() for m in self.memories],
            "refused": [r.to_public_dict() for r in self.refusals],
            "stored_count": len(self.memories),
            "refused_count": len(self.refusals),
        }
