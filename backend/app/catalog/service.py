from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.catalog.index import Catalog
from app.catalog.loader import CatalogError, load_dir
from app.config import get_settings

log = logging.getLogger(__name__)


def catalog_dir() -> Path:
    s = get_settings()
    return Path(s.catalog_dir) if s.catalog_dir else Path(s.kb_dir) / "catalog"


@lru_cache
def get_catalog() -> Catalog:
    """Loads the YAML files once. A broken file must not take the chat down: log it and use an
    empty catalog (run `python -m app.catalog.cli validate` to see the error)."""
    try:
        return Catalog(load_dir(catalog_dir()))
    except CatalogError as exc:
        log.error("SAP catalog not loaded: %s", exc)
        return Catalog([])


def reset_catalog() -> None:
    get_catalog.cache_clear()
