<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-lockup-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-lockup.svg">
    <img src="docs/assets/logo-lockup.svg" alt="Rakho" width="420">
  </picture>
</p>

<p align="center">
  <em>rakho (रखो) = "keep it."</em>
</p>

<p align="center">
  A memory database for AI agents. Inspect before you keep. Forget for real.<br>
  Talk to it in the language you actually think in.
</p>

## Why this exists

Agents are starting to remember people across chats. That is useful until the notebook also keeps an API key, someone else's ticket, or a poisoned line like "forget the safety rules."

Most memory layers **save first, search later**. The dangerous stuff is already in the box.

Rakho is the agent's diary with a bouncer at the door:

1. Check the note. Secret, personal, shady → do not write it down.
2. If it is safe, keep it, tagged with **whose** notebook it is.
3. Later, only that person's notes come back.
4. "Forget me" deletes the pages. Embeddings too.
5. You can look: what was kept, what was refused, what is left.

It is a library, not a server. Any developer can drop it in as their agent's memory. You do not need Sluice. You do not need a vector-DB cluster.

```python
from rakho import Rakho

db = Rakho("memory.db")

db.keep("order is late", actor_id="ankit")
db.keep("password is hunter2", actor_id="ankit")   # refused

db.recall("order", actor_id="ankit")               # late order, no password
db.forget(actor_id="ankit")                        # gone
db.audit(actor_id="ankit")                         # empty, and you can prove it
```

Every write needs `actor_id`. That is how Ankit's notebook never leaks into Priya's.

## The fun part: write commands in your language

The database has **four actions**. English is canonical so anyone can read the code. Hindi ships because that is the name. German ships because that is where it was built. They are the same four verbs, not three databases.

| | English | Hindi | German |
|---|---|---|---|
| keep it | `keep` / `store` | `rakho` | `merk` / `behalte` |
| pull it out | `recall` / `get` | `nikaalo` | `hol` / `abruf` |
| forget it | `forget` | `bhoolo` | `vergiss` |
| look | `audit` / `look` | `dekho` | `schau` / `zeig` |

```python
db.rakho("आर्डर लेट है", actor_id="ankit")
db.nikaalo("आर्डर", actor_id="ankit")
db.bhoolo(actor_id="ankit")
db.dekho(actor_id="ankit")

db.merk("Bestellung ist spät", actor_id="ankit")
db.hol("Bestellung", actor_id="ankit")
```

Same for the CLI. Mix freely. `nikaalo` is `recall`.

```bash
rakho keep --actor ankit "order is late"
rakho nikaalo --actor ankit "order"
rakho vergiss --actor ankit
rakho dekho --actor ankit
```

### Bring your own language

Commands are a dictionary. Add Swahili, Marathi, French, whatever you speak. New words call the same four actions. One word cannot mean two things.

```python
db.learn("swahili", {
    "keep": "weka",
    "recall": "leta",
    "forget": "sahau",
    "audit": "angalia",
})

db.weka("order is late", actor_id="ankit")
db.leta("order", actor_id="ankit")
```

```bash
rakho learn swahili --keep weka --recall leta --forget sahau --audit angalia
rakho weka --actor ankit "order is late"
```

The personality is the mouth. The rules stay in English underneath.

## Install

```bash
python3 -m pip install -e ".[dev]"
rakho
```

That last command is the front door: big wordmark, then four things to try.

```bash
python3 -m pytest -q
```

Try a scratch file:

```python
from rakho import Rakho

db = Rakho("/tmp/rakho-demo.db")
print(db.rakho("my order is late", actor_id="ankit"))
print([m.content for m in db.nikaalo("order", actor_id="ankit")])
```

```bash
python3 test_file.py
python3 examples/agent.py
```

## Embeddings (no local model)

Default is an offline hashing embedder so `pip install` works with no download and no key.

Hugging Face is **not a free embeddings API anymore**. Free accounts get no useful inference credit (PRO is paid). Do not plan on HF for day-to-day.

Use **Jina** instead: multilingual (`jina-embeddings-v3`, including Hindi and German), HTTPS, no weights on disk. Free API key: [jina.ai/embeddings](https://jina.ai/embeddings)

```bash
export JINA_API_KEY="jina_…"
rakho --embedder auto keep --actor ankit "order is late"
```

```python
db = Rakho("memory.db", embedder="auto")   # Jina if JINA_API_KEY, else HF if HF_TOKEN, else hash
db = Rakho("memory.db", embedder="jina")   # requires JINA_API_KEY
db = Rakho("memory.db", embedder="hf")     # requires HF_TOKEN; model intfloat/multilingual-e5-small
```

Same notes stay in SQLite. Only the vector source changes.

## Sluice (optional gate)

Rakho's default gate is always on. Sluice is a stronger inspector you can plug into the same slot — not 2FA, not required.

```bash
pip install sluice-taint
rakho --gate sluice keep --actor ankit "order is late"
```

```python
from rakho.sluice_gate import SluiceGate
db = Rakho("memory.db", gate=SluiceGate())
```

## MCP (optional)

For agents that cannot `import rakho` (Claude Desktop, Cursor):

```bash
pip install "rakho[mcp]"
rakho-mcp --db memory.db --embedder auto
```

Tools: `keep` / `rakho`, `recall` / `nikaalo`, `forget` / `bhoolo`, `audit` / `dekho`.

## v1

- Default gate is **on** (secrets, obvious PII, injection-shaped content). Gate first, embed after.
- Episodes only: raw notes, one owner each. No summaries.
- Forget is a real delete. Audit shows stored **and** refused (refusals never contain the secret).
- Zero runtime dependencies. SQLite on disk.

Locked idea: [rakho_onepager.md](rakho_onepager.md).
