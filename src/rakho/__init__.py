"""Rakho: agent memory that inspects before it keeps."""

from rakho.embeddings import (
    Embedder,
    HashingEmbedder,
    HuggingFaceEmbedder,
    JinaEmbedder,
    auto_embedder,
)
from rakho.gate import AllowAllGate, DefaultPolicyGate, PolicyGate
from rakho.models import AuditReport, Decision, ForgetResult, KeepResult, Memory, Refusal
from rakho.store import Rakho

__all__ = [
    "AllowAllGate",
    "AuditReport",
    "Decision",
    "DefaultPolicyGate",
    "Embedder",
    "ForgetResult",
    "HashingEmbedder",
    "HuggingFaceEmbedder",
    "JinaEmbedder",
    "KeepResult",
    "Memory",
    "PolicyGate",
    "Rakho",
    "Refusal",
    "auto_embedder",
]

__version__ = "0.1.0"
