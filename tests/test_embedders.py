from __future__ import annotations

from unittest.mock import patch

import pytest

from rakho.embeddings import HashingEmbedder, HuggingFaceEmbedder, JinaEmbedder, resolve_embedder


def test_hash_is_offline_default():
    e = resolve_embedder(None)
    assert isinstance(e, HashingEmbedder)
    v = e.embed("आर्डर लेट है", role="query")
    assert len(v) == 256
    assert abs(sum(x * x for x in v) - 1) < 1e-5


def test_jina_embedder_uses_http():
    fake = {"data": [{"embedding": [0.3, 0.4, 0.0]}]}
    with patch("rakho.embeddings._post_json", return_value=fake) as post:
        e = JinaEmbedder(api_key="jina_test", dimensions=3)
        vec = e.embed("order is late", role="query")
    assert post.call_args[0][1]["task"] == "retrieval.query"
    assert post.call_args[0][1]["model"] == "jina-embeddings-v3"
    assert len(vec) == 3


def test_hf_embedder_prefixes_e5_queries():
    fake = [[0.1, 0.2], [0.3, 0.4]]
    with patch("rakho.embeddings._post_json", return_value=fake) as post:
        e = HuggingFaceEmbedder(api_key="hf_test", model="intfloat/multilingual-e5-small")
        e.embed("order", role="query")
    assert post.call_args[0][1]["inputs"].startswith("query: ")


def test_unknown_embedder():
    with pytest.raises(ValueError, match="unknown embedder"):
        resolve_embedder("magic")
