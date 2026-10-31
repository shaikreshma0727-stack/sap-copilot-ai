"""FastAPI dependency for the routes that call the LLM: login is required, and the request is counted
against the usage limits. When a limit is reached the route still runs, but ask_llm() returns None."""

from fastapi import Depends

from app.aibudget import start_request
from app.deps import get_current_user
from app.models import User


async def ai_gate(user: User = Depends(get_current_user)) -> None:
    start_request(user.id)
