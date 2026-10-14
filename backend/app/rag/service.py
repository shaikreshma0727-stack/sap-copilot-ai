"""One shared Retriever for the whole app (loading the embedding model is slow)."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from app.config import get_settings
from app.rag.embedder import get_embedder
from app.rag.retriever import Retriever
from app.rag.store import KnowledgeStore

_lock = Lock()
_retriever: Retriever | None = None


def chroma_dir() -> Path:
    return Path(get_settings().kb_dir) / "chroma"


def make_store_and_embedder():
    s = get_settings()
    return KnowledgeStore(chroma_dir()), get_embedder(s.embedding_backend, s.embedding_model)


def get_retriever() -> Retriever:
    global _retriever
    with _lock:
        if _retriever is None:
            store, embedder = make_store_and_embedder()
            _retriever = Retriever(store, embedder)
        return _retriever


def reset_retriever() -> None:
    global _retriever
    with _lock:
        _retriever = None
