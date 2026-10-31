from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai_gate import ai_gate
from app.deps import get_current_user
from app.errors import explain as explain_mod
from app.errors.parser import MAX_INPUT_CHARS, parse
from app.errors.service import get_entries, match
from app.models import User

router = APIRouter(prefix="/errors", tags=["errors"])


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=3, max_length=MAX_INPUT_CHARS)


class MatchOut(BaseModel):
    id: str
    title: str
    causes: list[str]
    fix_steps: list[str]
    tcodes: list[str]
    status: Literal["verified", "documented", "unverified"]
    source: str


class AnalyzeOut(BaseModel):
    parsed: dict
    matches: list[MatchOut]
    explanation: str | None
    note: str


@router.post("/analyze", response_model=AnalyzeOut, dependencies=[Depends(ai_gate)])
def analyze(payload: AnalyzeRequest, _: User = Depends(get_current_user)):
    text = payload.text.strip()
    parsed = parse(text)
    entries = match(text, parsed)
    explanation = explain_mod.explain(text, parsed, entries)

    notes = []
    if not entries:
        notes.append("No entry in the error knowledge base matched this text.")
    elif any(e.status == "unverified" for e in entries):
        notes.append("Matched entries are general SAP knowledge written by the assistant and not yet verified against SAP documentation.")
    if explanation is None:
        notes.append("AI explanation is not available (no LLM key, the usage limit was reached, or the call failed); only the extracted facts and matched entries are shown.")
    else:
        notes.append("The AI explanation can be wrong. Check it against the dump itself and your system before acting.")

    return AnalyzeOut(
        parsed=parsed.as_dict(),
        matches=[MatchOut(**e.model_dump(include=set(MatchOut.model_fields))) for e in entries],
        explanation=explanation,
        note=" ".join(notes),
    )


@router.get("/coverage")
def coverage(_: User = Depends(get_current_user)):
    entries = get_entries()
    return {
        "entries": len(entries),
        "runtime_errors": sorted({r for e in entries for r in e.runtime_errors}),
    }
