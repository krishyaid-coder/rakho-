# Rakho

**Tagline:** Agent memory that inspects before it keeps, and can prove what it forgot.

*rakho (रखो) = "keep it."*

---

## Locked idea

Rakho is a small embeddable database for **what an AI agent is allowed to remember**.

It is a library, not a server. Any developer can use it as their agent's memory. Sluice is not required. Sluice is one bouncer that can plug in later.

It is **not** Sluice's SQLite. Sluice logs what the gate blocked (fingerprints, decisions). Rakho stores recallable notes ("Krishy's order is late") after a gate says they are safe.

v1 stores **episodes only** — raw notes, one owner each. No summaries, no extracted facts, no custom storage engine.

---

## The four actions

English is canonical. Hindi and German ship in the box. Anyone can add a language pack; new words call the same four actions.

| action | English | Hindi | German |
|--------|---------|-------|--------|
| keep   | `keep` / `store` | `rakho` | `merk` / `behalte` |
| recall | `recall` / `get` | `nikaalo` | `hol` / `abruf` |
| forget | `forget` | `bhoolo` | `vergiss` |
| audit  | `audit` / `look` | `dekho` | `schau` / `zeig` |

```python
db.keep(content, actor_id="krishy")
db.learn("swahili", {"keep": "weka", "recall": "leta", "forget": "sahau", "audit": "angalia"})
```

Commands are a dictionary. The database does not change.

---

## Rules (non-negotiable)

1. **Gate first, embed after.** Default gate is on (secrets, obvious PII, injection-shaped content). Fail closed. No-op exists for tests only.
2. **Every write needs `actor_id`.** `scope` defaults to `"default"`. Recall cannot cross that boundary.
3. **Forget is a real delete** (row + FTS + embedding). `forget()` with no target is refused.
4. **Audit shows stored and refused.** Refusals never contain the secret itself — only a mask and a reason.
5. **Episodes only.** No `kind: summary` until lineage exists.

---

## Data model

```python
Memory:
  id: uuid
  content: str              # recallable text (already gated)
  embedding: vector
  kind: "episode"           # v1: only this
  source, session_id, origin_tool: optional
  actor_id: str             # required
  scope: str
  created_at, last_used_at: ts
  sensitivity: clean | redacted
  metadata: json

Refusal:
  id, actor_id, scope, reason, labels, preview, created_at
  # preview is masked; never the raw secret
```

---

## Architecture

```python
class PolicyGate:
    def inspect(content, context) -> Decision
    # Decision = {action: store | redact | skip, sensitivity, reason, content}

class StorageEngine:
    def put(memory)
    def search(query, query_vec, filters, k)
    def delete(filter)
    def refusals(...)
```

- `keep` → gate → embed allowed text → `put` (or record a refusal)
- `recall` → hybrid search (keyword + vector + recency) inside actor/scope → pack to a token budget
- `forget` / `audit` work because provenance is indexed

v1 storage: SQLite + FTS5. Vectors as blobs; cosine in process. Swap the engine later behind the same interface.

---

## v1 demo (the bar)

1. Krishy: "my order is late. password is hunter2" → keep the order, refuse the password.
2. Recall "order" for Krishy → late order, no password.
3. Priya has her own note. Forget Krishy → his rows are gone, including refusals. Priya untouched.
4. `audit(actor_id="krishy")` is empty.

Ship when that is boringly reliable.

---

## Not in v1 / still not in 0.2

Custom HNSW engine, derived facts/summaries, decay, natural-language sentences as queries, hosted embeddings, a bundled embedding model.

Sluice gate, MCP, and remote embeddings (Jina / HF) are optional extras. Default remains offline hash + built-in gate. `gate="sluice"` is the enable step. The default gate covers English / Hindi / German secrets, Aadhaar, PAN, Steuer-ID, and injection-shaped lines.

---

## Stack

Python 3.10+, stdlib SQLite, zero required runtime dependencies. Embedder is swappable: hash (offline), Jina (`jina-embeddings-v3` over HTTPS), or Hugging Face (`multilingual-e5-small` over HTTPS). Do not download a local model.
