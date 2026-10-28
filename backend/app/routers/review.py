from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models import User
from app.quality import abaplint_check
from app.review import assess as assess_mod
from app.review.rules import review as run_rules

router = APIRouter(prefix="/review", tags=["review"])

MAX_CODE_CHARS = 15000
_FENCE = re.compile(r"^\s*```[ \t]*(abap)?[ \t]*\r?\n(.*?)\r?\n?```\s*$", re.DOTALL | re.IGNORECASE)


class ReviewRequest(BaseModel):
    code: str = Field(min_length=10, max_length=MAX_CODE_CHARS)


class FindingOut(BaseModel):
    rule: str
    severity: str
    line: int
    title: str
    why: str
    suggestion: str
    code: str


class SyntaxOut(BaseModel):
    line: int
    message: str


class ReviewOut(BaseModel):
    lines: int
    findings: list[FindingOut]
    syntax_checked: bool
    syntax: list[SyntaxOut]
    review: str | None
    note: str


def _clean(code: str) -> str:
    m = _FENCE.match(code)
    return (m.group(2) if m else code).strip("\n")


@router.post("/code", response_model=ReviewOut)
def review_code(payload: ReviewRequest, _: User = Depends(get_current_user)):
    code = _clean(payload.code)
    findings = [f.as_dict() for f in run_rules(code)]

    issues = abaplint_check.check_blocks([code]) if abaplint_check.is_available() else None
    syntax = [{"line": i.line, "message": i.message} for i in (issues or [])]

    ai = assess_mod.assess(code, findings, None if issues is None else syntax)

    notes = ["The findings come from fixed pattern rules on the text. They can be wrong (false positives) and they cannot see table types, data volumes or your system; this is not a replacement for ATC / Code Inspector."]
    if issues is None:
        notes.append("The abaplint syntax check is not installed here, so grammar and declaration errors were not checked.")
    if ai is None:
        notes.append("The AI review is not available (no LLM key or the call failed); the rule findings are still shown.")
    else:
        notes.append("The AI review can be wrong. Check each point against the code.")
    return ReviewOut(
        lines=len(code.splitlines()),
        findings=[FindingOut(**f) for f in findings],
        syntax_checked=issues is not None,
        syntax=[SyntaxOut(**s) for s in syntax],
        review=ai,
        note=" ".join(notes),
    )
