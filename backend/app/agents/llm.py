"""LLM access. Returns None when no API key is configured so the app (and tests)
still run without any external service."""

from functools import lru_cache

from app.aibudget import ai_allowed
from app.config import get_settings


@lru_cache
def get_llm():
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    from langchain_groq import ChatGroq  # imported lazily: only needed with a key

    extra = {"max_tokens": settings.llm_max_tokens} if settings.llm_max_tokens else {}
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.2,
        **extra,
    )


def ask_llm(system_prompt: str, user_message: str) -> str | None:
    """Call the LLM. Returns None if no key is set, the usage limit is reached or the call fails."""
    if not ai_allowed():
        return None
    llm = get_llm()
    if llm is None:
        return None
    try:
        result = llm.invoke([("system", system_prompt), ("human", user_message)])
        return str(result.content)
    except Exception:
        return None
