from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.errors.loader import ErrorBankError, load_dir
from app.errors.models import ErrorEntry
from app.errors.parser import Parsed

log = logging.getLogger(__name__)


def errors_dir() -> Path:
    s = get_settings()
    return Path(s.errors_dir) if s.errors_dir else Path(s.kb_dir) / "errors"


@lru_cache
def get_entries() -> list[ErrorEntry]:
    try:
        return load_dir(errors_dir())
    except ErrorBankError as exc:
        log.error("Error knowledge not loaded: %s", exc)
        return []


def reset_entries() -> None:
    get_entries.cache_clear()


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", text) is not None


def match(text: str, parsed: Parsed, entries: list[ErrorEntry] | None = None, limit: int = 3) -> list[ErrorEntry]:
    """Rank knowledge entries by how much evidence in the text points at them.

    Runtime error name = strongest signal (10), exception class = 6, a message phrase = 3 each.
    """
    entries = get_entries() if entries is None else entries
    low = text.lower()
    scored: list[tuple[int, ErrorEntry]] = []
    for e in entries:
        score = 0
        for r in e.runtime_errors:
            if r == parsed.runtime_error or _has_word(text, r):
                score += 10
                break
        for x in e.exceptions:
            if x == parsed.exception or _has_word(text, x):
                score += 6
                break
        score += 3 * sum(1 for ph in e.phrases if ph in low)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return [e for _, e in scored[:limit]]
