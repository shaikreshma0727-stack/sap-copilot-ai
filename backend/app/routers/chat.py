from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_copilot
from app.database import get_db
from app.deps import get_current_user
from app.models import ChatMessage, User
from app.schemas import ChatHistoryItem, ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = run_copilot(payload.message)
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
