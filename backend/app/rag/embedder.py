"""Embedding backends.

- fastembed (default): runs the BAAI/bge-small-en-v1.5 model through ONNX. No PyTorch
  needed, which avoids the CPU/CUDA install problems seen on Mac/Docker. The model
  (~130 MB) is downloaded on first use and cached.
- hash: a tiny deterministic offline embedder. NOT semantic; it exists so tests and
  CI can exercise the whole pipeline without downloading a model.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.rag.tokenize import tokenize


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, query: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding  # imported lazily: heavy

        self.name = f"fastembed:{model_name}"
        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # bge-v1.5 needs no prefix on passages (only on queries), so plain embed() is right here
        return [v.tolist() for v in self._model.embed(texts, batch_size=32)]

    def embed_query(self, query: str) -> list[float]:
        # query_embed adds the retrieval instruction prefix that bge models expect
        return next(iter(self._model.query_embed(query))).tolist()


class HashEmbedder:
    """Bag-of-hashed-words vectors. Deterministic, offline, test-only."""

    def __init__(self, dim: int = 256):
        self.name = f"hash:{dim}"
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in tokenize(text):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._vec(query)


def get_embedder(backend: str = "fastembed", model_name: str = "BAAI/bge-small-en-v1.5") -> Embedder:
    if backend == "hash":
        return HashEmbedder()
    if backend == "fastembed":
        return FastEmbedEmbedder(model_name)
    raise ValueError(f"Unknown EMBEDDING_BACKEND '{backend}' (use 'fastembed' or 'hash')")
