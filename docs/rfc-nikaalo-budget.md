# RFC: `nikaalo` should say when notes were skipped

Status: **proposal** (this PR). No code yet. Comment here before we implement.

`nikaalo` / `recall` already packs hits into a token bag (default **512**). Notes that do not fit are dropped for that call. They stay in SQLite. The caller is not told. The next call is a new search, not “send what you skipped.”

That is a silent skip. The agent can think it remembered something it never saw.

This is **not** a dollar-cost dashboard. Jina cents per session are a rounding error. The cost that hurts is tokens stuffed into the next model call — and tokens left in the box with no signal.

## Example

Krishy’s notebook has three notes. Pretend each is 300 tokens. Budget is 512.

1. “vendor invoice 4000 USD”
2. “order is late”
3. “BLOCKED attacker payee”

`nikaalo("invoice")` today:

- Note 1 goes in (300).
- Note 2 would make 600 → **not sent**.
- Note 3 never gets in.

The agent only sees note 1. Notes 2 and 3 are still in the database. Nobody says so.

Next `nikaalo("invoice")` searches again from scratch. It may send note 1 again and skip 2 and 3 again. The leftover 600 is **not** rolled over.

## What we will ship

1. **Tell the truth.** Every `nikaalo` reports packed tokens, budget, how many hits were skipped, and whether more remain.

   ```text
   packed 300 / 512   skipped 2   more=yes
   ```

   Python keeps working as a list of memories (`for m in db.nikaalo(...)`). Extra fields live on the result (`skipped`, `packed_tokens`, `budget`, `cursor`).

2. **Same question, next page.** A second `nikaalo("invoice", cursor=...)` means “give me what you skipped for this query,” not “search from zero and send note 1 again.”

`dekho` can show the same numbers for an actor (and `--session` if you passed one). Scoreboard without (1) still leaves the agent half-blind, so we will not ship a look-only line.

## What we will not ship

- Auto-roll leftovers into the **next unrelated** call. “Is the order late?” must not get leftover invoice text just because the bag was full last time.
- LLM / Jina dollar receipts. Rakho does not see the chat bill.
- Summaries or compressing 900 tokens into 200. Still episodes only, until lineage exists.
- A fifth verb. This is still `nikaalo` / `dekho`.

## Why not only raise `--budget`

You can already pass `--budget`. That does not tell you that you needed to. Krishy’s PayPal run already mixed invoice text with payment ledger lines ([observation 5](../examples/paypal/SIMULATION.md)). A fatter bag still fails closed-eyed.

## Sketch (not implemented)

```python
page = db.nikaalo("invoice", actor_id="krishy")
page.packed_tokens   # 300
page.budget          # 512
page.skipped         # 2
page.cursor          # opaque; None if nothing left

if page.cursor:
    rest = db.nikaalo("invoice", actor_id="krishy", cursor=page.cursor)
```

```bash
rakho --db memory.db nikaalo --actor krishy "invoice"
# vendor invoice 4000 USD
# packed 300/512  skipped 2  more=yes

rakho --db memory.db nikaalo --actor krishy --cursor CURSOR "invoice"
```

Forget still deletes the rows, the index, the vectors, and any page cursor that pointed at them.

## Out of this RFC

Scoping `origin_tool=read_file` vs `create_invoice` so invoices and payments do not share one bag. Real, but a different change.
