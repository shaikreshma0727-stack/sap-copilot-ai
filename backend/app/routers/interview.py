from __future__ import annotations

from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.interview import judge as judge_mod
from app.interview.scoring import MAX_SCORE, add_ai_coverage, evaluate
from app.interview.service import get_bank, pick_question
from app.models import InterviewAttempt, User

router = APIRouter(prefix="/interview", tags=["interview"])


class QuestionRequest(BaseModel):
    topic: str | None = None
    level: Literal["basic", "intermediate", "advanced"] | None = None
    exclude_id: str | None = None  # the question on screen now, so "next" never repeats it


class QuestionOut(BaseModel):
    id: str
    topic: str
    level: str
    question: str
    key_point_count: int


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=4000)


class CoveredPoint(BaseModel):
    text: str
    by: Literal["keywords", "ai"]


class AnswerOut(BaseModel):
    score: float
    max_score: float
    covered: list[CoveredPoint]
    missed: list[str]
    feedback: str
    model_answer: str
    too_short: bool = False
    scoring_note: str


@router.get("/topics")
def topics(_: User = Depends(get_current_user)):
    out: dict[str, dict] = {}
    for q in get_bank().values():
        t = out.setdefault(q.topic, {"topic": q.topic, "count": 0, "levels": set()})
        t["count"] += 1
        t["levels"].add(q.level)
    return sorted(
        ({"topic": t["topic"], "count": t["count"], "levels": sorted(t["levels"])} for t in out.values()),
        key=lambda t: t["topic"],
    )


@router.post("/question", response_model=QuestionOut)
def next_question(payload: QuestionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bank = get_bank()
    if not bank:
        raise HTTPException(status_code=503, detail="No interview questions loaded (see knowledge_base/interview)")
    rows = db.execute(
        select(InterviewAttempt.question_id, func.count()).where(InterviewAttempt.user_id == user.id).group_by(InterviewAttempt.question_id)
    ).all()
    q = pick_question(bank, dict(rows), payload.topic, payload.level, payload.exclude_id)
    if q is None:
        raise HTTPException(status_code=404, detail="No question matches that topic/level")
    return QuestionOut(id=q.id, topic=q.topic, level=q.level, question=q.question, key_point_count=len(q.key_points))


@router.post("/answer", response_model=AnswerOut)
def answer(payload: AnswerRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = get_bank().get(payload.question_id.strip().lower())
    if q is None:
        raise HTTPException(status_code=404, detail="Unknown question")
    ev = evaluate(q, payload.answer)
    feedback = ""
    if ev.too_short:
        feedback = "Your answer is very short. Explain it in a few sentences, as you would in a real interview."
    else:
        j = judge_mod.judge(q, payload.answer, ev.missed)
        if j:
            ev = add_ai_coverage(q, ev, j.also_covered)
            feedback = j.feedback
        else:
            feedback = "AI feedback is not available right now (no LLM key or the call failed); the score below uses keyword matching only."
    db.add(
        InterviewAttempt(
            user_id=user.id, question_id=q.id, topic=q.topic, level=q.level, answer=payload.answer, score=ev.score
        )
    )
    db.commit()
    return AnswerOut(
        score=ev.score,
        max_score=MAX_SCORE,
        covered=[CoveredPoint(text=q.key_points[i].text, by=by) for i, by in ev.covered],
        missed=[q.key_points[i].text for i in ev.missed],
        feedback=feedback,
        model_answer=q.model_answer,
        too_short=ev.too_short,
        scoring_note="Score = share of the expected key points your answer covered (keyword match, plus an AI check of the missed ones). It is not a grade of overall quality.",
    )


@router.get("/progress")
def progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attempts = list(db.scalars(select(InterviewAttempt).where(InterviewAttempt.user_id == user.id).order_by(InterviewAttempt.id.desc())))
    by_topic: dict[str, list[float]] = defaultdict(list)
    for a in attempts:
        by_topic[a.topic].append(a.score)
    topics = sorted(
        ({"topic": t, "attempts": len(s), "average": round(sum(s) / len(s), 1)} for t, s in by_topic.items()),
        key=lambda t: t["topic"],
    )
    weakest = [t["topic"] for t in sorted(topics, key=lambda t: (t["average"], t["topic"]))[:3] if t["average"] < 7]
    bank = get_bank()
    return {
        "attempts": len(attempts),
        "average": round(sum(a.score for a in attempts) / len(attempts), 1) if attempts else None,
        "max_score": MAX_SCORE,
        "by_topic": topics,
        "weakest": weakest,
        "recent": [
            {
                "question": bank[a.question_id].question if a.question_id in bank else a.question_id,
                "topic": a.topic,
                "score": a.score,
                "at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attempts[:10]
        ],
    }
