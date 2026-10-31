from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_copilot
from app.database import get_db
from app.ai_gate import ai_gate
from app.aibudget import LIMIT_MESSAGE, ai_allowed
from app.deps import get_current_user
from app.models import ChatMessage, User
from app.schemas import ChatHistoryItem, ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, dependencies=[Depends(ai_gate)])
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = run_copilot(payload.message)
    if not ai_allowed():
        result["answer"] = f"{LIMIT_MESSAGE}\n\n{result['answer']}"
    db.add(
        ChatMessage(
            user_id=current_user.id,
            question=payload.message,
            answer=result["answer"],
            agent=result["agent"],
        )
    )
    db.commit()
    return ChatResponse(**result)


@router.get("/history", response_model=list[ChatHistoryItem])
def history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.id.desc())
        .limit(min(limit, 200))
    )
    return list(db.scalars(stmt))
