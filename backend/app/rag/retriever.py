"""Hybrid retrieval: vector search + BM25 keyword search, merged with Reciprocal Rank Fusion.

Why both? Vector search understands meaning ("create a purchase requisition"),
BM25 nails exact names (BAPI_REQUISITION_CREATE, EBAN). SAP work needs both.
"""

from __future__ import annotations

from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.rag.embedder import Embedder
from app.rag.store import KnowledgeStore
from app.rag.tokenize import tokenize

RRF_K = 60  # standard constant from the RRF paper


@dataclass
class Hit:
    id: str
    score: float
    text: str
    metadata: dict
    vector_rank: int | None = None
    bm25_rank: int | None = None


class Retriever:
    def __init__(self, store: KnowledgeStore, embedder: Embedder):
        self.store = store
        self.embedder = embedder
        self._bm25: BM25Okapi | None = None
        self._ids: list[str] = []
        self._docs: list[str] = []
        self._metas: list[dict] = []
        self._indexed_count = -1

    # ---- BM25 index (rebuilt automatically when the store size changes) ----
    def _ensure_bm25(self) -> None:
        count = self.store.count()
        if count == self._indexed_count:
            return
        self._ids, self._docs, self._metas = self.store.all_documents()
        corpus = [tokenize(d) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._indexed_count = count

    def refresh(self) -> None:
        self._indexed_count = -1

    @staticmethod
    def _matches(meta: dict, filters: dict | None) -> bool:
        return not filters or all(meta.get(k) == v for k, v in filters.items() if v is not None)

    def _bm25_search(self, query: str, n: int, filters: dict | None):
        self._ensure_bm25()
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            if self._matches(self._metas[i], filters):
                out.append(i)
                if len(out) >= n:
                    break
        return out

    def search(
        self,
        query: str,
        k: int = 5,
        mode: str = "hybrid",
        filters: dict | None = None,
        candidates: int = 30,
    ) -> list[Hit]:
        if mode not in ("hybrid", "vector", "bm25"):
            raise ValueError("mode must be 'hybrid', 'vector' or 'bm25'")
        if self.store.count() == 0:
            return []

        hits: dict[str, Hit] = {}

        if mode in ("hybrid", "vector"):
            ids, docs, metas, _ = self.store.query(self.embedder.embed_query(query), candidates, filters)
            for rank, (i, d, m) in enumerate(zip(ids, docs, metas), 1):
                hits[i] = Hit(id=i, score=0.0, text=d, metadata=m, vector_rank=rank)

        if mode in ("hybrid", "bm25"):
            self._ensure_bm25()
            for rank, idx in enumerate(self._bm25_search(query, candidates, filters), 1):
                cid = self._ids[idx]
                if cid in hits:
                    hits[cid].bm25_rank = rank
                else:
                    hits[cid] = Hit(id=cid, score=0.0, text=self._docs[idx], metadata=self._metas[idx], bm25_rank=rank)

        for h in hits.values():
            if h.vector_rank:
                h.score += 1.0 / (RRF_K + h.vector_rank)
            if h.bm25_rank:
                h.score += 1.0 / (RRF_K + h.bm25_rank)

        return sorted(hits.values(), key=lambda h: h.score, reverse=True)[:k]
