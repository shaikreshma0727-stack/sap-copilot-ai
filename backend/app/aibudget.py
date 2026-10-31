"""Usage limits for AI calls, so a public demo cannot drain the shared LLM quota.

Counting is per request (one chat message may need two LLM calls, it still counts once).
Limits live in memory: they reset when the server restarts and are not shared between several
server processes. That is fine for a one-instance demo; use Redis or a database table for more.
A limit of 0 means "no limit"."""

from __future__ import annotations

import contextvars
import threading
import time
from collections import deque

from app.config import get_settings

LIMIT_MESSAGE = (
    "The AI usage limit of this demo was reached (it protects the shared free API quota), so this answer "
    "has no AI part. Try again later."
)

_allowed: contextvars.ContextVar[bool] = contextvars.ContextVar("ai_allowed", default=True)


class Limiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._per_user: dict[int, deque[float]] = {}
        self._day = ""
        self._day_count = 0

    def reset(self) -> None:
        with self._lock:
            self._per_user.clear()
            self._day, self._day_count = "", 0

    def consume(self, user_id: int, per_hour: int, per_day: int, now: float | None = None) -> bool:
        """Record one AI request. Returns False (and records nothing) when a limit is used up."""
        now = time.time() if now is None else now
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self._lock:
            if today != self._day:
                self._day, self._day_count = today, 0
            hits = self._per_user.setdefault(user_id, deque())
            while hits and hits[0] <= now - 3600:
                hits.popleft()
            if per_hour > 0 and len(hits) >= per_hour:
                return False
            if per_day > 0 and self._day_count >= per_day:
                return False
            hits.append(now)
            self._day_count += 1
            return True


_limiter = Limiter()


def llm_configured() -> bool:
    return bool(get_settings().groq_api_key)


def start_request(user_id: int) -> bool:
    """Called once at the start of an AI request. Returns True when AI may be used for it."""
    ok = True
    if llm_configured():
        s = get_settings()
        ok = _limiter.consume(user_id, s.ai_limit_per_hour, s.ai_limit_per_day)
    _allowed.set(ok)
    return ok


def ai_allowed() -> bool:
    return _allowed.get()


def reset_limits() -> None:
    _limiter.reset()
