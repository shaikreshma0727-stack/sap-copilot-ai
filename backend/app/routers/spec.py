from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models import User
from app.spec import checklist
from app.spec import draft as draft_mod
from app.spec.detect import detect

router = APIRouter(prefix="/spec", tags=["spec"])

MAX_FS_CHARS = 15000


class GenerateRequest(BaseModel):
    fs_text: str = Field(min_length=40, max_length=MAX_FS_CHARS)


class TopicOut(BaseModel):
    id: str
    label: str
    mentioned: bool
    question: str


class GenerateOut(BaseModel):
    topics: list[TopicOut]
    coverage: str
    detected: dict
    draft: str | None
    note: str


@router.post("/generate", response_model=GenerateOut)
def generate(payload: GenerateRequest, _: User = Depends(get_current_user)):
    text = payload.fs_text.strip()
    topics = checklist.evaluate(text)
    detected = detect(text)
    missing = [t["label"] + " - " + t["question"] for t in topics if not t["mentioned"]]
    draft = draft_mod.generate(text, detected, missing)

    notes = ["The topic check looks for keywords: 'mentioned' does not mean the FS describes the topic well."]
    if any(o["status"] == "unverified" for o in detected["catalog_objects"]):
        notes.append("Catalog objects found are unverified general knowledge; confirm names in SE11/SE37.")
    if draft is None:
        notes.append("The AI draft is not available (no LLM key or the call failed); the topic check and detected objects are still shown.")
    else:
        notes.append("The draft can be wrong or incomplete. Review every table, field and rule against the FS and your system, and take the Open questions to the functional consultant.")
    return GenerateOut(
        topics=[TopicOut(**t) for t in topics],
        coverage=checklist.summary(topics),
        detected=detected,
        draft=draft,
        note=" ".join(notes),
    )
