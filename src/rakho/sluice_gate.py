from __future__ import annotations

import re
from typing import Any, Callable

from rakho.gate import PolicyGate
from rakho.models import Decision

_SKIP_PREFIXES = ("prompt_injection", "tool_poisoning")
_USEFUL_MIN = 8


class SluiceGate(PolicyGate):
    """Optional PolicyGate: Sluice's detectors inspect before a memory is kept.

    Rakho still works without this. Install sluice-taint and pass gate=SluiceGate().
    """

    def __init__(self, scanner: Callable[..., list[Any]] | None = None) -> None:
        if scanner is None:
            _require_sluice()
            scanner = _sluice_scan
        self._scan = scanner

    def inspect(self, content: str, context: dict[str, Any] | None = None) -> Decision:
        if not content or not content.strip():
            return Decision(action="skip", content="", reason="empty", labels=["empty"])

        ctx = context or {}
        hits = self._scan(content, ctx)
        if not hits:
            return Decision(action="store", content=content, reason="clean")

        labels: list[str] = []
        skip = False
        redacted = content
        # Apply from the end so offsets stay valid.
        ordered = sorted(hits, key=lambda h: getattr(h, "start", 0), reverse=True)
        for hit in ordered:
            detector = str(getattr(hit, "detector_id", getattr(hit, "label", "sluice")))
            family = detector.split(".", 1)[0]
            leaf = detector.split(".", 1)[-1].replace(" ", "_")
            # Keep the family name for injection/poisoning so origin tagging
            # can see prompt_injection, not just ignore_instructions.
            label = family if family in _SKIP_PREFIXES else leaf
            if label not in labels:
                labels.append(label)
            if any(detector.startswith(p) or family.startswith(p) for p in _SKIP_PREFIXES):
                skip = True
            start = int(getattr(hit, "start", 0))
            end = int(getattr(hit, "end", start))
            if 0 <= start < end <= len(redacted):
                redacted = redacted[:start] + f"[REDACTED:{label}]" + redacted[end:]

        if skip:
            return Decision(action="skip", content="", reason="sluice_block", labels=labels)

        remainder = re.sub(r"\[REDACTED:[^\]]+\]", " ", redacted)
        remainder = re.sub(r"\s+", " ", remainder).strip(" :;,-.")
        if len(remainder) < _USEFUL_MIN:
            return Decision(action="skip", content="", reason="sluice_secret_or_pii", labels=labels)
        return Decision(
            action="redact",
            content=redacted,
            reason="sluice:" + ",".join(labels),
            labels=labels,
        )


def _require_sluice() -> None:
    try:
        import sluice  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Sluice is not installed. pip install sluice-taint  "
            "(optional — Rakho's default gate works without it)"
        ) from exc


def _sluice_scan(content: str, context: dict[str, Any]) -> list[Any]:
    _require_sluice()
    from sluice.detectors import pii, prompt_injection, secrets, tool_poisoning  # noqa: F401
    from sluice.detectors.base import ScanContext, scan_all

    # Keep is ingesting untrusted content (often a tool response). Sluice's
    # prompt_injection detector only runs on response / tools/call.
    scan_ctx = ScanContext(
        direction="response",
        method="tools/call",
        tool=context.get("origin_tool") or "rakho",
        upstream="rakho",
        session_id=str(context.get("session_id") or "default"),
    )
    return scan_all(content, scan_ctx)
