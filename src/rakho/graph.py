"""Look at one actor's recall. Never draws another actor's notes.

CLI prints an ASCII tree. Mermaid is for GitHub / mermaid.live — terminals
do not render it.
"""

from __future__ import annotations

from rakho.models import Memory, Mutation, Refusal

_BOX = 52


def _label(text: str, limit: int = 42) -> str:
    cleaned = " ".join(text.split())
    for src, dst in (
        ("\"", "'"),
        ("[", "("),
        ("]", ")"),
        ("{", "("),
        ("}", ")"),
        ("|", "/"),
        ("<", ""),
        (">", ""),
        ("\n", " "),
    ):
        cleaned = cleaned.replace(src, dst)
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned or "(empty)"


def _edge(mem: Memory) -> str:
    return (
        f"vec {mem.vec_score:.2f} · keyword {mem.fts_score:.2f} · "
        f"recency {mem.recency_score:.2f}"
    )


def _note_line(mem: Memory, kind: str) -> str:
    dim = len(mem.embedding) if mem.embedding else 0
    who = mem.embedder or "-"
    return f"{kind} · {dim}d {who} · {_label(mem.content)}"


def _box(lines: list[str], *, width: int = _BOX, stem: bool = False) -> list[str]:
    inner = width - 2
    out = ["┌" + "─" * inner + "┐"]
    for line in lines:
        text = _label(line, inner - 2)
        out.append("│ " + text.ljust(inner - 2) + " │")
    if stem:
        pad = inner // 2
        out.append("└" + "─" * pad + "┬" + "─" * (inner - pad - 1) + "┘")
    else:
        out.append("└" + "─" * inner + "┘")
    return out


def _stem(text: str, *, width: int = _BOX) -> list[str]:
    col = (width // 2) - 1
    bar = " " * col + "│"
    return [bar, bar + "  " + text, " " * col + "▼"]


def _query_lines(query: str, packed_tokens: int, budget: int, skipped: int) -> list[str]:
    if not query.strip():
        return ["dekho · no query"]
    return [
        f"query · {_label(query, 36)}",
        f"packed {packed_tokens}/{budget} · skipped {skipped}",
    ]


def _refusal_lines(ref: Refusal) -> list[str]:
    return [f"refused · {_label(ref.reason, 20)}", _label(ref.preview)]


def build_ascii(
    *,
    actor_id: str,
    query: str,
    packed: list[Memory],
    skipped: list[Memory],
    orphaned: list[Memory],
    forgotten_ids: list[str],
    unranked: list[Memory] | None = None,
    refused: list[Refusal] | None = None,
    packed_tokens: int = 0,
    budget: int = 512,
) -> str:
    unranked = unranked or []
    refused = refused or []
    lines = [f"notebook {_label(actor_id, 24)}", ""]
    hits: list[tuple[list[str], str | None]] = []
    title = _query_lines(query, packed_tokens, budget, len(skipped))
    if query.strip():
        if not packed and not skipped:
            hits.append((["no trusted hit"], None))
        for mem in packed:
            hits.append(([_note_line(mem, "packed")], _edge(mem)))
        for mem in skipped:
            hits.append(([_note_line(mem, "skipped · bag full")], _edge(mem)))
    else:
        for mem in packed:
            hits.append(([_note_line(mem, "stored")], None))

    extras: list[tuple[list[str], str | None]] = []
    for mem in unranked:
        extras.append((["didn't rank", _label(mem.content)], None))
    for ref in refused:
        extras.append((_refusal_lines(ref), None))
    for mem in orphaned:
        extras.append((["orphaned · dekho only", _label(mem.content)], None))
    for mid in forgotten_ids:
        short = (mid[:8] + "…") if mid else "?"
        extras.append(([f"forgotten · {short}", "row and vector gone"], None))

    chain = hits + extras
    lines.extend(_box(title, stem=bool(chain)))
    if not chain:
        return "\n".join(lines) + "\n"

    for i, (body, edge) in enumerate(chain):
        last = i == len(chain) - 1
        if edge:
            lines.extend(_stem(edge))
        else:
            col = (_BOX // 2) - 1
            lines.append(" " * col + "│")
            lines.append(" " * col + "▼")
        lines.extend(_box(body, stem=not last))
    return "\n".join(lines) + "\n"


def build_mermaid(
    *,
    actor_id: str,
    query: str,
    packed: list[Memory],
    skipped: list[Memory],
    orphaned: list[Memory],
    forgotten_ids: list[str],
    unranked: list[Memory] | None = None,
    refused: list[Refusal] | None = None,
    packed_tokens: int = 0,
    budget: int = 512,
) -> str:
    unranked = unranked or []
    refused = refused or []
    q = "<br/>".join(_query_lines(query, packed_tokens, budget, len(skipped)))
    lines = [
        "flowchart TB",
        f'  subgraph actor["notebook { _label(actor_id, 24) }"]',
        f'    Q["{q}"]',
    ]
    if query.strip():
        if not packed and not skipped:
            lines.append('    Q --> Empty["no trusted hit"]')
        for i, mem in enumerate(packed):
            nid = f"P{i}"
            lines.append(f'    {nid}["{_note_line(mem, "packed")}"]')
            lines.append(f'    Q -->|{_edge(mem)}| {nid}')
        for i, mem in enumerate(skipped):
            nid = f"S{i}"
            lines.append(f'    {nid}["{_note_line(mem, "skipped · bag full")}"]')
            lines.append(f'    Q -->|{_edge(mem)}| {nid}')
    else:
        for i, mem in enumerate(packed):
            lines.append(f'    P{i}["{_note_line(mem, "stored")}"]')
    lines.append("  end")

    if unranked:
        lines.append('  subgraph miss["didn\'t rank"]')
        for i, mem in enumerate(unranked):
            lines.append(f'    U{i}["didn\'t rank · {_label(mem.content)}"]')
        lines.append("  end")

    if refused:
        lines.append('  subgraph door["refused at the door"]')
        for i, ref in enumerate(refused):
            lines.append(
                f'    R{i}["refused · {_label(ref.reason, 20)} · {_label(ref.preview)}"]'
            )
        lines.append("  end")

    if orphaned:
        lines.append('  subgraph held["not trusted · dekho only"]')
        for i, mem in enumerate(orphaned):
            lines.append(f'    O{i}["orphaned · {_label(mem.content)}"]')
        lines.append("  end")

    if forgotten_ids:
        lines.append('  subgraph gone["removed · row and vector gone"]')
        for i, mid in enumerate(forgotten_ids):
            short = mid[:8] if mid else "?"
            lines.append(f'    F{i}["forgotten · {short}…"]')
        lines.append("  end")

    return "\n".join(lines) + "\n"


def forgotten_ids_from(mutations: list[Mutation]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for mut in mutations:
        if mut.op != "forget":
            continue
        raw = mut.detail.get("deleted_ids") or []
        if isinstance(raw, str):
            raw = [raw]
        for item in raw:
            if item and item not in seen:
                seen.add(item)
                ids.append(item)
        if mut.target_id and mut.target_id not in seen:
            seen.add(mut.target_id)
            ids.append(mut.target_id)
    return ids
