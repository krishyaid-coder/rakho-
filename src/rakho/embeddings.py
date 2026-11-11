from __future__ import annotations

import hashlib
import json
import math
import os
import ssl
import struct
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class Embedder(ABC):
    dim: int | None = None

    @abstractmethod
    def embed(self, text: str, *, role: str = "document") -> list[float]:
        raise NotImplementedError

    def serialize(self, vector: list[float]) -> bytes:
        return struct.pack(f"<{len(vector)}f", *vector)

    def deserialize(self, blob: bytes) -> list[float]:
        n = len(blob) // 4
        return list(struct.unpack(f"<{n}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class HashingEmbedder(Embedder):
    """Offline fallback. No download, no API. Crude, but Hindi/German still hash."""

    def __init__(self, dim: int = 256, ngram: int = 3) -> None:
        self.dim = dim
        self.ngram = ngram

    def embed(self, text: str, *, role: str = "document") -> list[float]:
        vec = [0.0] * self.dim
        s = text.casefold()
        if len(s) < self.ngram:
            s = s.ljust(self.ngram)
        for i in range(len(s) - self.ngram + 1):
            gram = s[i : i + self.ngram].encode("utf-8")
            digest = hashlib.blake2b(gram, digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        return l2_normalize(vec)


def _ssl_context() -> ssl.SSLContext:
    """python.org macOS installs often ship with no CA bundle. Use certifi if present."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float = 30) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"embed HTTP {exc.code} from {url}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "CERTIFICATE_VERIFY_FAILED" in reason:
            raise RuntimeError(
                "embed SSL failed (macOS python.org has no CA bundle). "
                "python3 -m pip install certifi   "
                "or run Install Certificates.command in /Applications/Python 3.13/"
            ) from exc
        raise RuntimeError(f"embed request failed: {exc.reason}") from exc


def _as_vector(payload: Any) -> list[float]:
    if isinstance(payload, dict) and "data" in payload:
        return [float(x) for x in payload["data"][0]["embedding"]]
    if isinstance(payload, list):
        if not payload:
            raise RuntimeError("embedder returned an empty vector")
        first = payload[0]
        if isinstance(first, (int, float)):
            return [float(x) for x in payload]
        if isinstance(first, list):
            if first and isinstance(first[0], (int, float)):
                dim = len(first)
                acc = [0.0] * dim
                for tok in payload:
                    for i, v in enumerate(tok):
                        acc[i] += float(v)
                n = max(len(payload), 1)
                return [x / n for x in acc]
            return _as_vector(first)
    raise RuntimeError(f"unexpected embedding payload: {type(payload)!r}")


class JinaEmbedder(Embedder):
    """jina-embeddings-v3 over HTTPS. Free API key, no model download.

    Covers English, Hindi, German. Get a key at https://jina.ai/embeddings
    """

    DEFAULT_MODEL = "jina-embeddings-v3"
    URL = "https://api.jina.ai/v1/embeddings"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        dimensions: int = 256,
        timeout: float = 30,
    ) -> None:
        self.api_key = api_key or os.environ.get("JINA_API_KEY") or os.environ.get("JINA_API_TOKEN")
        if not self.api_key:
            raise RuntimeError(
                "Jina embedder needs JINA_API_KEY. Free key: https://jina.ai/embeddings"
            )
        self.model = model
        self.dimensions = dimensions
        self.dim = dimensions
        self.timeout = timeout

    def embed(self, text: str, *, role: str = "document") -> list[float]:
        task = "retrieval.query" if role == "query" else "retrieval.passage"
        payload = {
            "model": self.model,
            "task": task,
            "input": [text],
            "dimensions": self.dimensions,
        }
        raw = _post_json(
            self.URL,
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        return l2_normalize(_as_vector(raw))


class HuggingFaceEmbedder(Embedder):
    """HF Inference Providers feature-extraction. Needs HF_TOKEN.

    Hugging Face free accounts no longer include useful inference credit.
    This is here for people who already have a token / PRO. Default model is
    multilingual-e5-small (English, Hindi, German) — still no local download.
    """

    DEFAULT_MODEL = "intfloat/multilingual-e5-small"
    ROUTER = "https://router.huggingface.co/hf-inference/models"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 45,
    ) -> None:
        self.api_key = api_key or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        if not self.api_key:
            raise RuntimeError("Hugging Face embedder needs HF_TOKEN")
        self.model = model
        self.timeout = timeout
        self.dim = None

    def embed(self, text: str, *, role: str = "document") -> list[float]:
        body = text
        if "e5" in self.model.lower():
            prefix = "query: " if role == "query" else "passage: "
            body = prefix + text
        url = f"{self.ROUTER}/{self.model}"
        raw = _post_json(
            url,
            {"inputs": body, "normalize": True, "truncate": True},
            {"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        return l2_normalize(_as_vector(raw))


def auto_embedder() -> Embedder:
    """Pick a remote embedder from env, else stay offline."""
    if os.environ.get("JINA_API_KEY") or os.environ.get("JINA_API_TOKEN"):
        return JinaEmbedder()
    if os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"):
        return HuggingFaceEmbedder()
    return HashingEmbedder()


def resolve_embedder(embedder: Embedder | str | None) -> Embedder:
    if embedder is None or embedder == "hash":
        return HashingEmbedder()
    if isinstance(embedder, Embedder):
        return embedder
    name = str(embedder).strip().lower()
    if name == "auto":
        return auto_embedder()
    if name == "jina":
        return JinaEmbedder()
    if name in {"hf", "huggingface", "e5"}:
        return HuggingFaceEmbedder()
    raise ValueError(f"unknown embedder '{embedder}'. use hash, auto, jina, or hf")
