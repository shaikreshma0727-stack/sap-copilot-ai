"""Persistent vector store (ChromaDB, local folder, no server to run)."""

from __future__ import annotations

from pathlib import Path

COLLECTION = "sap_kb"


def build_where(filters: dict | None) -> dict | None:
    """Turn {'module': 'MM', 'technology': 'rap'} into a Chroma where-clause."""
    if not filters:
        return None
    items = [{k: v} for k, v in filters.items() if v is not None]
    if not items:
        return None
    return items[0] if len(items) == 1 else {"$and": items}


class KnowledgeStore:
    def __init__(self, persist_dir: str | Path, collection: str = COLLECTION):
        import chromadb  # imported lazily: heavy

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        # embedding_function=None: we always compute embeddings ourselves (see embedder.py),
        # so Chroma never tries to download its own default model.
        self._col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def count(self) -> int:
        return self._col.count()

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict], embeddings: list[list[float]]):
        self._col.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    def delete_source(self, source: str) -> None:
        self._col.delete(where={"source": source})

    def reset(self) -> None:
        self._client.delete_collection(self._col.name)
        self._col = self._client.get_or_create_collection(
            name=self._col.name, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def all_documents(self) -> tuple[list[str], list[str], list[dict]]:
        ids, docs, metas = [], [], []
        offset, page = 0, 1000
        while True:
            r = self._col.get(limit=page, offset=offset, include=["documents", "metadatas"])
            if not r["ids"]:
                break
            ids += r["ids"]
            docs += r["documents"]
            metas += r["metadatas"]
            offset += page
        return ids, docs, metas

    def query(self, embedding: list[float], n: int, filters: dict | None = None):
        total = self.count()
        if total == 0:
            return [], [], [], []
        r = self._col.query(
            query_embeddings=[embedding],
            n_results=min(n, total),
            where=build_where(filters),
            include=["documents", "metadatas", "distances"],
        )
        return r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0]

    def source_counts(self) -> dict[str, int]:
        _, _, metas = self.all_documents()
        out: dict[str, int] = {}
        for m in metas:
            out[m.get("source", "?")] = out.get(m.get("source", "?"), 0) + 1
        return out
