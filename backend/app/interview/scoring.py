from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.interview.models import KeyPoint, Question

MIN_WORDS = 5
MAX_SCORE = 10.0


@dataclass
class Evaluation:
    score: float
    covered: list[tuple[int, str]] = field(default_factory=list)  # (key point index, "keywords" | "ai")
    missed: list[int] = field(default_factory=list)
    too_short: bool = False


def _found(answer_low: str, keyword: str) -> bool:
    parts = [p.strip() for p in keyword.split("+") if p.strip()]
    return bool(parts) and all(re.search(r"(?<![\w])" + re.escape(p), answer_low) for p in parts)


def point_covered(point: KeyPoint, answer: str) -> bool:
    low = answer.lower()
    return any(_found(low, k) for k in point.any)


def score_of(covered: int, total: int) -> float:
    return round(MAX_SCORE * covered / total, 1) if total else 0.0


def evaluate(question: Question, answer: str) -> Evaluation:
    """Keyword coverage only. The AI check of missed points is applied afterwards via add_ai_coverage."""
    total = len(question.key_points)
    if len(answer.split()) < MIN_WORDS:
        return Evaluation(score=0.0, missed=list(range(total)), too_short=True)
    covered = [(i, "keywords") for i, p in enumerate(question.key_points) if point_covered(p, answer)]
    done = {i for i, _ in covered}
    return Evaluation(
        score=score_of(len(covered), total),
        covered=covered,
        missed=[i for i in range(total) if i not in done],
    )


def add_ai_coverage(question: Question, ev: Evaluation, indices: list[int]) -> Evaluation:
    """Move points the AI judged as covered (only ones that were missed) into 'covered'."""
    valid = [i for i in dict.fromkeys(indices) if i in ev.missed]
    if not valid:
        return ev
    covered = sorted(ev.covered + [(i, "ai") for i in valid])
    done = {i for i, _ in covered}
    total = len(question.key_points)
    return Evaluation(
        score=score_of(len(covered), total),
        covered=covered,
        missed=[i for i in range(total) if i not in done],
        too_short=ev.too_short,
    )
