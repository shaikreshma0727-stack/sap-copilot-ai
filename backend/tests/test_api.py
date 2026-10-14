import os

# Use an isolated SQLite file and no LLM key for tests (must be set before importing the app).
os.environ["DATABASE_URL"] = "sqlite:///./test_sap_copilot.db"
os.environ["GROQ_API_KEY"] = ""
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123456"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.router_agent import keyword_route  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:  # runs lifespan -> creates tables
        yield c
    Base.metadata.drop_all(bind=engine)


def _register_and_login(client, email="reshma@example.com", password="StrongPass123"):
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": "Reshma"})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_duplicate_email_rejected(client):
    _register_and_login(client)
    r = client.post("/auth/register", json={"email": "reshma@example.com", "password": "StrongPass123"})
    assert r.status_code == 400


def test_login_wrong_password(client):
    _register_and_login(client)
    r = client.post("/auth/login", data={"username": "reshma@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    headers = _register_and_login(client)
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "reshma@example.com"


def test_chat_routes_and_saves_history(client):
    headers = _register_and_login(client)
    r = client.post("/chat", json={"message": "Create an ABAP program with ALV using BAPI"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["agent"] == "abap"

    r = client.post("/chat", json={"message": "Give me SAP MM interview questions"}, headers=headers)
    assert r.json()["agent"] == "learning"

    r = client.get("/chat/history", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_chat_requires_login(client):
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Explain this ABAP code and fix the short dump in ST22", "abap"),
        ("Explain the procure to pay business process", "functional"),
        ("Give me a study roadmap for SAP certification", "learning"),
        ("hello there", "learning"),
    ],
)
def test_keyword_router(message, expected):
    assert keyword_route(message) == expected
