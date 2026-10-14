from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import get_current_user
from app.models import User
from app.rag.service import get_retriever

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


class SearchHit(BaseModel):
    id: str
    score: float
    text: str
    metadata: dict
    vector_rank: int | None = None
    bm25_rank: int | None = None


@router.get("/search", response_model=list[SearchHit])
def search(
    q: str = Query(min_length=2, max_length=500),
    k: int = Query(5, ge=1, le=20),
    mode: Literal["hybrid", "vector", "bm25"] = "hybrid",
    module: str | None = None,
    technology: str | None = None,
    object_type: str | None = None,
    source: str | None = None,
    _: User = Depends(get_current_user),
):
    """Search the SAP knowledge base. Optional filters narrow results by metadata."""
    filters = {"module": module, "technology": technology, "object_type": object_type, "source": source}
    try:
        hits = get_retriever().search(q, k=k, mode=mode, filters=filters)
    except Exception as exc:  # e.g. embedding model could not be downloaded
        raise HTTPException(status_code=503, detail=f"Knowledge base unavailable: {exc}") from exc
    return [SearchHit(**h.__dict__) for h in hits]
