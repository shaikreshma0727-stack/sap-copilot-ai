from fastapi import APIRouter, Depends, HTTPException, Query

from app.catalog.models import Entry
from app.catalog.service import get_catalog
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/stats")
def stats(_: User = Depends(get_current_user)):
    return get_catalog().stats()


@router.get("/search", response_model=list[Entry])
def search(q: str = Query(min_length=2, max_length=300), limit: int = Query(5, ge=1, le=20), _: User = Depends(get_current_user)):
    """Entries whose name appears in q, then entries whose keywords/description match."""
    return get_catalog().search(q, limit=limit)


@router.get("/{name}", response_model=Entry)
def get_entry(name: str, _: User = Depends(get_current_user)):
    entry = get_catalog().get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{name.upper()} is not in the catalog")
    return entry
