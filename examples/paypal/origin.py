"""Origin gate from the PayPal × Sluice hackathon.

A money call is blocked when its payee can be traced back to content
that already tripped a detector in this session.

Fingerprints, not raw emails. PII-only hits do not tag — a normal
invoice email is not itself a taint mark.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Same rule as the hackathon: tag on injection / poisoning / secrets.
# Default-gate secret labels sit here so origin works without sluice-taint.
_TAG_ON = (
    "prompt_injection",
    "tool_poisoning",
    "secrets",
    "private_key",
    "openai_key",
    "github_token",
    "github_pat",
    "aws_key",
    "slack_token",
    "bearer",
    "password",
)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def fingerprint(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()[:16]


def mask_email(email: str) -> str:
    local, _, domain = normalize_email(email).partition("@")
    if not domain:
        return "***"
    head = local[:3] if local else ""
    return f"{head}***@{domain}"


def extract_emails(text: str) -> list[str]:
    seen: list[str] = []
    found: set[str] = set()
    for raw in _EMAIL.findall(text):
        key = normalize_email(raw)
        if key not in found:
            found.add(key)
            seen.append(key)
    return seen


def should_tag(labels: list[str]) -> bool:
    return any(
        any(label == prefix or label.startswith(prefix) for prefix in _TAG_ON)
        for label in labels
    )


@dataclass
class OriginHit:
    fingerprint: str
    mask: str
    labels: list[str]
    source: str | None = None


@dataclass
class OriginIndex:
    """Per-session fingerprint index. Not a blocklist of accounts."""

    _hits: dict[str, OriginHit] = field(default_factory=dict)

    def tag(self, content: str, labels: list[str], *, source: str | None = None) -> list[OriginHit]:
        if not should_tag(labels):
            return []
        tagged: list[OriginHit] = []
        for email in extract_emails(content):
            fp = fingerprint(email)
            hit = OriginHit(
                fingerprint=fp,
                mask=mask_email(email),
                labels=list(labels),
                source=source,
            )
            self._hits[fp] = hit
            tagged.append(hit)
        return tagged

    def check(self, payee: str) -> OriginHit | None:
        return self._hits.get(fingerprint(payee))

    def __len__(self) -> int:
        return len(self._hits)
