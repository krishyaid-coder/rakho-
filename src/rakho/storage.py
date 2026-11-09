from __future__ import annotations

import json
import re
import sqlite3
import struct
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from rakho.embeddings import cosine
from rakho.models import Memory, Refusal, utcnow


SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding BLOB,
    kind TEXT NOT NULL DEFAULT 'episode',
    source TEXT,
    session_id TEXT,
    actor_id TEXT NOT NULL,
    origin_tool TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    scope TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memories_actor_scope ON memories(actor_id, scope);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    memory_id UNINDEXED,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS refusals (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    reason TEXT NOT NULL,
    labels TEXT NOT NULL DEFAULT '[]',
    preview TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refusals_actor_scope ON refusals(actor_id, scope);

CREATE TABLE IF NOT EXISTS verb_packs (
    language TEXT NOT NULL,
    action TEXT NOT NULL,
    verb TEXT NOT NULL,
    PRIMARY KEY (language, action, verb)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_verb_unique ON verb_packs(verb);
"""


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class StorageEngine(ABC):
    @abstractmethod
    def put(self, memory: Memory) -> None:
        raise NotImplementedError

    @abstractmethod
    def put_refusal(self, refusal: Refusal) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query: str,
        query_vec: list[float] | None,
        *,
        actor_id: str,
        scope: str,
        k: int,
    ) -> list[Memory]:
        raise NotImplementedError

    @abstractmethod
    def list_memories(self, *, actor_id: str, scope: str | None = None) -> list[Memory]:
        raise NotImplementedError

    @abstractmethod
    def list_refusals(self, *, actor_id: str, scope: str | None = None) -> list[Refusal]:
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        *,
        actor_id: str | None = None,
        scope: str | None = None,
        session_id: str | None = None,
        id: str | None = None,
    ) -> tuple[int, int]:
        raise NotImplementedError

    @abstractmethod
    def touch(self, ids: Iterable[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_verbs(self, language: str, verbs: dict[str, list[str]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def all_verbs(self) -> dict[str, str]:
        """verb -> action"""
        raise NotImplementedError


class SQLiteEngine(StorageEngine):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def put(self, memory: Memory) -> None:
        blob = None
        if memory.embedding is not None:
            blob = struct.pack(f"<{len(memory.embedding)}f", *memory.embedding)
        self._conn.execute(
            """
            INSERT INTO memories (
                id, content, embedding, kind, source, session_id, actor_id,
                origin_tool, created_at, last_used_at, sensitivity, scope, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                blob,
                memory.kind,
                memory.source,
                memory.session_id,
                memory.actor_id,
                memory.origin_tool,
                memory.created_at.isoformat(),
                memory.last_used_at.isoformat(),
                memory.sensitivity,
                memory.scope,
                json.dumps(memory.metadata),
            ),
        )
        self._conn.execute(
            "INSERT INTO memories_fts (content, memory_id) VALUES (?, ?)",
            (memory.content, memory.id),
        )
        self._conn.commit()

    def put_refusal(self, refusal: Refusal) -> None:
        self._conn.execute(
            """
            INSERT INTO refusals (id, actor_id, scope, reason, labels, preview, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                refusal.id,
                refusal.actor_id,
                refusal.scope,
                refusal.reason,
                json.dumps(refusal.labels),
                refusal.preview,
                refusal.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def _row_to_memory(self, row: sqlite3.Row, embedding: list[float] | None = None) -> Memory:
        blob = row["embedding"]
        vec = embedding
        if vec is None and blob is not None:
            n = len(blob) // 4
            vec = list(struct.unpack(f"<{n}f", blob))
        return Memory(
            id=row["id"],
            content=row["content"],
            embedding=vec,
            kind=row["kind"],
            source=row["source"],
            session_id=row["session_id"],
            actor_id=row["actor_id"],
            origin_tool=row["origin_tool"],
            created_at=_parse_ts(row["created_at"]),
            last_used_at=_parse_ts(row["last_used_at"]),
            sensitivity=row["sensitivity"],
            scope=row["scope"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def search(
        self,
        query: str,
        query_vec: list[float] | None,
        *,
        actor_id: str,
        scope: str,
        k: int,
    ) -> list[Memory]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE actor_id = ? AND scope = ?",
            (actor_id, scope),
        ).fetchall()
        if not rows:
            return []

        fts_scores: dict[str, float] = {}
        match_query = _fts_match_query(query)
        if match_query:
            try:
                fts_rows = self._conn.execute(
                    """
                    SELECT memories_fts.memory_id AS id,
                           bm25(memories_fts) AS rank
                    FROM memories_fts
                    JOIN memories ON memories.id = memories_fts.memory_id
                    WHERE memories_fts MATCH ?
                      AND memories.actor_id = ?
                      AND memories.scope = ?
                    """,
                    (match_query, actor_id, scope),
                ).fetchall()
                if fts_rows:
                    worst = max(abs(r["rank"]) for r in fts_rows) or 1.0
                    for r in fts_rows:
                        # bm25: more negative is better in sqlite fts5
                        fts_scores[r["id"]] = 1.0 - (abs(r["rank"]) / (worst + 1e-9))
            except sqlite3.OperationalError:
                like = f"%{query}%"
                for r in self._conn.execute(
                    """
                    SELECT id FROM memories
                    WHERE actor_id = ? AND scope = ? AND content LIKE ?
                    """,
                    (actor_id, scope, like),
                ):
                    fts_scores[r["id"]] = 1.0

        now = utcnow()
        scored: list[Memory] = []
        for row in rows:
            mem = self._row_to_memory(row)
            vec_score = 0.0
            if query_vec is not None and mem.embedding is not None:
                vec_score = max(0.0, cosine(query_vec, mem.embedding))
            fts_score = fts_scores.get(mem.id, 0.0)
            age_hours = max(0.0, (now - mem.created_at).total_seconds() / 3600.0)
            recency = 1.0 / (1.0 + age_hours / 24.0)
            mem.score = 0.5 * vec_score + 0.3 * fts_score + 0.2 * recency
            # keyword miss still can rank via vector/recency; keep all, sort, cut
            scored.append(mem)

        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:k]

    def list_memories(self, *, actor_id: str, scope: str | None = None) -> list[Memory]:
        if scope is None:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE actor_id = ? ORDER BY created_at DESC",
                (actor_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE actor_id = ? AND scope = ? ORDER BY created_at DESC",
                (actor_id, scope),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def list_refusals(self, *, actor_id: str, scope: str | None = None) -> list[Refusal]:
        if scope is None:
            rows = self._conn.execute(
                "SELECT * FROM refusals WHERE actor_id = ? ORDER BY created_at DESC",
                (actor_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM refusals WHERE actor_id = ? AND scope = ? ORDER BY created_at DESC",
                (actor_id, scope),
            ).fetchall()
        return [
            Refusal(
                id=r["id"],
                actor_id=r["actor_id"],
                scope=r["scope"],
                reason=r["reason"],
                labels=json.loads(r["labels"] or "[]"),
                preview=r["preview"],
                created_at=_parse_ts(r["created_at"]),
            )
            for r in rows
        ]

    def delete(
        self,
        *,
        actor_id: str | None = None,
        scope: str | None = None,
        session_id: str | None = None,
        id: str | None = None,
    ) -> tuple[int, int]:
        where: list[str] = []
        params: list[Any] = []
        if id:
            where.append("id = ?")
            params.append(id)
        if actor_id:
            where.append("actor_id = ?")
            params.append(actor_id)
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if not where:
            raise ValueError("delete refused: no filter")

        clause = " AND ".join(where)
        ids = [
            r["id"]
            for r in self._conn.execute(
                f"SELECT id FROM memories WHERE {clause}", params
            ).fetchall()
        ]
        for memory_id in ids:
            self._conn.execute(
                "DELETE FROM memories_fts WHERE rowid IN "
                "(SELECT rowid FROM memories_fts WHERE memory_id = ?)",
                (memory_id,),
            )
        cur = self._conn.execute(f"DELETE FROM memories WHERE {clause}", params)
        memories_deleted = cur.rowcount if cur.rowcount != -1 else len(ids)

        ref_where: list[str] = []
        ref_params: list[Any] = []
        if actor_id:
            ref_where.append("actor_id = ?")
            ref_params.append(actor_id)
        if scope:
            ref_where.append("scope = ?")
            ref_params.append(scope)
        # session_id / memory id do not apply to refusals
        refusals_deleted = 0
        if ref_where and not id and not session_id:
            ref_clause = " AND ".join(ref_where)
            cur = self._conn.execute(f"DELETE FROM refusals WHERE {ref_clause}", ref_params)
            refusals_deleted = cur.rowcount if cur.rowcount != -1 else 0
        elif id:
            pass

        self._conn.commit()
        return memories_deleted, refusals_deleted

    def touch(self, ids: Iterable[str]) -> None:
        now = utcnow().isoformat()
        for memory_id in ids:
            self._conn.execute(
                "UPDATE memories SET last_used_at = ? WHERE id = ?",
                (now, memory_id),
            )
        self._conn.commit()

    def add_verbs(self, language: str, verbs: dict[str, list[str]]) -> None:
        for action, words in verbs.items():
            for word in words:
                verb = word.strip().casefold()
                if not verb:
                    continue
                existing = self._conn.execute(
                    "SELECT action, language FROM verb_packs WHERE verb = ?",
                    (verb,),
                ).fetchone()
                if existing and existing["action"] != action:
                    raise ValueError(
                        f"verb '{word}' already means '{existing['action']}' "
                        f"(language={existing['language']})"
                    )
                if existing:
                    continue
                self._conn.execute(
                    "INSERT INTO verb_packs (language, action, verb) VALUES (?, ?, ?)",
                    (language, action, verb),
                )
        self._conn.commit()

    def all_verbs(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT verb, action FROM verb_packs").fetchall()
        return {r["verb"]: r["action"] for r in rows}


def _fts_match_query(query: str) -> str | None:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    if not tokens:
        return None
    return " OR ".join(tokens)
