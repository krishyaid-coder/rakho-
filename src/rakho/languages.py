from __future__ import annotations

ACTIONS = ("keep", "recall", "forget", "audit")

BUILT_IN: dict[str, dict[str, list[str]]] = {
    "en": {
        "keep": ["keep", "store"],
        "recall": ["recall", "get"],
        "forget": ["forget"],
        "audit": ["audit", "look"],
    },
    "hi": {
        "keep": ["rakho"],
        "recall": ["nikaalo"],
        "forget": ["bhoolo"],
        "audit": ["dekho"],
    },
    "de": {
        "keep": ["merk", "behalte"],
        "recall": ["hol", "abruf"],
        "forget": ["vergiss"],
        "audit": ["schau", "zeig"],
    },
}


def invert(packs: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    """verb -> action. Last write wins only within a single pack load; collisions raise."""
    out: dict[str, str] = {}
    owners: dict[str, str] = {}
    for language, mapping in packs.items():
        for action, words in mapping.items():
            if action not in ACTIONS:
                raise ValueError(f"unknown action '{action}'")
            for word in words:
                verb = word.strip().casefold()
                if verb in out and out[verb] != action:
                    raise ValueError(
                        f"verb '{word}' collides: {out[verb]} vs {action} ({language}/{owners[verb]})"
                    )
                out[verb] = action
                owners[verb] = language
    return out


def normalize_pack(verbs: dict[str, str | list[str]]) -> dict[str, list[str]]:
    missing = [a for a in ACTIONS if a not in verbs]
    if missing:
        raise ValueError(f"language pack missing actions: {missing}")
    extra = [k for k in verbs if k not in ACTIONS]
    if extra:
        raise ValueError(f"language pack has unknown actions: {extra}")
    out: dict[str, list[str]] = {}
    for action in ACTIONS:
        value = verbs[action]
        words = [value] if isinstance(value, str) else list(value)
        if not words:
            raise ValueError(f"language pack needs a word for '{action}'")
        out[action] = words
    return out
