from __future__ import annotations

import logging
import random
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.interview.loader import QuestionBankError, load_dir
from app.interview.models import Question

log = logging.getLogger(__name__)


def interview_dir() -> Path:
    s = get_settings()
    return Path(s.interview_dir) if s.interview_dir else Path(s.kb_dir) / "interview"


@lru_cache
def get_bank() -> dict[str, Question]:
    try:
        return {q.id: q for q in load_dir(interview_dir())}
    except QuestionBankError as exc:
        log.error("Interview questions not loaded: %s", exc)
        return {}


def reset_bank() -> None:
    get_bank.cache_clear()


def pick_question(
    bank: dict[str, Question],
    attempts_per_question: dict[str, int],
    topic: str | None = None,
    level: str | None = None,
    exclude_id: str | None = None,
    rng: random.Random | None = None,
) -> Question | None:
    """Prefer questions the user has answered least; random among equals."""
    rng = rng or random.Random()
    pool = [
        q
        for q in bank.values()
        if (not topic or q.topic.lower() == topic.lower())
        and (not level or q.level == level)
        and q.id != exclude_id
    ]
    if not pool:
        return None
    fewest = min(attempts_per_question.get(q.id, 0) for q in pool)
    return rng.choice([q for q in pool if attempts_per_question.get(q.id, 0) == fewest])
