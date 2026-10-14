"""/kb/search endpoint. conftest.py points KB_DIR at a temp folder and uses the hash embedder."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_kb.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rag.ingest import ingest_folder  # noqa: E402
from app.rag.service import make_store_and_embedder, reset_retriever  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    Base.metadata.drop_all(bind=engine)
    reset_retriever()
    src = tmp_path / "notes"
    src.mkdir()
    (src / "pr.md").write_text(
        "# Purchase requisition\n\nUse BAPI_PR_CREATE to create a purchase requisition in the MM module. Table EBAN holds items.",
        encoding="utf-8",
    )
    store, embedder = make_store_and_embedder()
    store.reset()
    ingest_folder(src, "notes", store, embedder)
    reset_retriever()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    reset_retriever()


def _auth(client):
    client.post("/auth/register", json={"email": "kb@example.com", "password": "StrongPass123"})
    token = client.post("/auth/login", data={"username": "kb@example.com", "password": "StrongPass123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_search_requires_login(client):
    assert client.get("/kb/search", params={"q": "BAPI_PR_CREATE"}).status_code == 401


def test_search_returns_ranked_hits(client):
    r = client.get("/kb/search", params={"q": "BAPI_PR_CREATE", "k": 3}, headers=_auth(client))
    assert r.status_code == 200
    hits = r.json()
    assert hits and "BAPI_PR_CREATE" in hits[0]["text"]
    assert hits[0]["metadata"]["module"] == "MM"


def test_search_filters_and_validation(client):
    h = _auth(client)
    assert client.get("/kb/search", params={"q": "requisition", "module": "FI", "mode": "bm25"}, headers=h).json() == []
    assert client.get("/kb/search", params={"q": "x"}, headers=h).status_code == 422  # too short
    assert client.get("/kb/search", params={"q": "requisition", "mode": "weird"}, headers=h).status_code == 422
