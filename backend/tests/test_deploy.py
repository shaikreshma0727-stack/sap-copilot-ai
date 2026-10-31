"""Usage limits, DATABASE_URL / CORS handling and the RAG-off guard of the hosted demo."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_deploy.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import aibudget  # noqa: E402
from app.aibudget import LIMIT_MESSAGE, Limiter  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

# ---- Limiter -------------------------------------------------------------------------------


def test_hourly_limit_is_per_user_and_slides():
    lim = Limiter()
    t = 1_000_000.0
    assert lim.consume(1, 2, 0, now=t)
    assert lim.consume(1, 2, 0, now=t + 10)
    assert not lim.consume(1, 2, 0, now=t + 20)
    assert lim.consume(2, 2, 0, now=t + 20)  # another user is not affected
    assert lim.consume(1, 2, 0, now=t + 3601)  # the first request left the window


def test_daily_limit_is_global_and_resets_at_utc_midnight():
    lim = Limiter()
    day1 = 1_700_000_000.0  # 2023-11-14 22:13 UTC
    assert lim.consume(1, 0, 3, now=day1)
    assert lim.consume(2, 0, 3, now=day1 + 1)
    assert lim.consume(3, 0, 3, now=day1 + 2)
    assert not lim.consume(4, 0, 3, now=day1 + 3)
    assert lim.consume(4, 0, 3, now=day1 + 4 * 3600)  # next UTC day


def test_zero_means_unlimited():
    lim = Limiter()
    assert all(lim.consume(1, 0, 0, now=1000.0 + i) for i in range(500))


def test_a_refused_request_is_not_counted():
    lim = Limiter()
    assert lim.consume(1, 1, 5, now=100.0)
    for i in range(10):
        assert not lim.consume(1, 1, 5, now=101.0 + i)
    assert lim.consume(2, 1, 5, now=200.0)  # the day counter did not move on refusals


# ---- Through the real routes ---------------------------------------------------------------


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content="FAKE-AI-ANSWER")


@pytest.fixture()
def client(monkeypatch):
    get_settings.cache_clear()
    aibudget.reset_limits()
    Base.metadata.drop_all(bind=engine)
    fake = FakeLLM()
    monkeypatch.setattr("app.agents.llm.get_llm", lambda: fake)
    monkeypatch.setattr(
        aibudget, "get_settings", lambda: SimpleNamespace(groq_api_key="x", ai_limit_per_hour=1, ai_limit_per_day=0)
    )
    with TestClient(app) as c:
        c.fake = fake
        yield c
    Base.metadata.drop_all(bind=engine)
    aibudget.reset_limits()
    get_settings.cache_clear()


def _auth(client, email="lim@example.com"):
    client.post("/auth/register", json={"email": email, "password": "StrongPass123"})
    token = client.post("/auth/login", data={"username": email, "password": "StrongPass123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_chat_degrades_after_the_limit(client):
    h = _auth(client)
    first = client.post("/chat", json={"message": "What is a BAdI in SAP?"}, headers=h).json()
    assert "FAKE-AI-ANSWER" in first["answer"] and LIMIT_MESSAGE not in first["answer"]
    calls_after_first = client.fake.calls
    second = client.post("/chat", json={"message": "What is a BAdI in SAP?"}, headers=h).json()
    assert second["answer"].startswith(LIMIT_MESSAGE)
    assert "FAKE-AI-ANSWER" not in second["answer"]
    assert client.fake.calls == calls_after_first  # the LLM was not called again


def test_other_user_still_gets_ai(client):
    client.post("/chat", json={"message": "What is a BAdI in SAP?"}, headers=_auth(client, "a@example.com"))
    other = client.post("/chat", json={"message": "What is a BAdI in SAP?"}, headers=_auth(client, "b@example.com")).json()
    assert "FAKE-AI-ANSWER" in other["answer"]


def test_error_analyzer_note_mentions_the_limit(client):
    h = _auth(client)
    body = {"text": "Runtime error: DBIF_RSQL_SQL_ERROR, short dump in program ZTEST"}
    ok = client.post("/errors/analyze", json=body, headers=h).json()
    assert ok["explanation"] == "FAKE-AI-ANSWER"
    blocked = client.post("/errors/analyze", json=body, headers=h).json()
    assert blocked["explanation"] is None
    assert "usage limit" in blocked["note"]


def test_ai_routes_still_require_login(client):
    assert client.post("/chat", json={"message": "hello there"}).status_code == 401
    assert client.post("/errors/analyze", json={"text": "x" * 50}).status_code == 401


def test_no_limit_counting_without_an_llm_key(monkeypatch):
    lim_before = aibudget._limiter._day_count
    monkeypatch.setattr(aibudget, "get_settings", lambda: SimpleNamespace(groq_api_key="", ai_limit_per_hour=1, ai_limit_per_day=1))
    assert aibudget.start_request(1) and aibudget.start_request(1)
    assert aibudget._limiter._day_count == lim_before


# ---- Config ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given,expected",
    [
        ("postgres://u:p@host/db?sslmode=require", "postgresql+psycopg2://u:p@host/db?sslmode=require"),
        ("postgresql://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("postgresql+psycopg2://u:p@host/db", "postgresql+psycopg2://u:p@host/db"),
        ("sqlite:///./x.db", "sqlite:///./x.db"),
    ],
)
def test_database_url_is_normalized(given, expected):
    assert Settings(database_url=given).database_url == expected


def test_limits_default_to_off():
    s = Settings()
    assert s.ai_limit_per_hour == 0 and s.ai_limit_per_day == 0


def test_cors_accepts_several_origins(monkeypatch):
    import importlib

    import app.main as main_mod

    monkeypatch.setenv("FRONTEND_ORIGIN", "https://a.example.app/, https://b.example.app")
    get_settings.cache_clear()
    try:
        reloaded = importlib.reload(main_mod)
        cors = [m for m in reloaded.app.user_middleware if m.cls.__name__ == "CORSMiddleware"][0]
        assert cors.kwargs["allow_origins"] == ["https://a.example.app", "https://b.example.app"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        importlib.reload(main_mod)


def test_kb_search_is_503_when_rag_is_off(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("RAG_ENABLED", "false")
    Base.metadata.drop_all(bind=engine)
    try:
        with TestClient(app) as c:
            c.post("/auth/register", json={"email": "kb@example.com", "password": "StrongPass123"})
            tok = c.post("/auth/login", data={"username": "kb@example.com", "password": "StrongPass123"}).json()["access_token"]
            r = c.get("/kb/search", params={"q": "badi"}, headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 503 and "RAG_ENABLED" in r.json()["detail"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        Base.metadata.drop_all(bind=engine)
