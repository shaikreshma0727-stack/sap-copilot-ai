"""FS to TS: checklist, object detection, API."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_spec.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.catalog.service import reset_catalog  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import spec as spec_router  # noqa: E402
from app.spec import checklist  # noqa: E402
from app.spec import draft as draft_mod  # noqa: E402
from app.spec.detect import detect, guess_type  # noqa: E402

FS_FULL = """Purpose: Purchasing needs a report of open purchase requisitions per plant.
Selection screen: plant (mandatory), purchasing group (select-option), creation date range.
Data is read from table EBAN and material descriptions from MAKT.
Rules: if the requisition is older than 30 days it is marked red. Validate that the plant exists.
Output: ALV grid with columns requisition, item, material, quantity, age in days.
Authorization: authority-check on M_BANF_WRK for the plant.
Error handling: if no data is found show message 'No open requisitions'.
Run online, about 50000 rows expected. Test: plant 1000 returns the sample data.
The program is called ZMM_OPEN_PR."""

FS_THIN = "Please make a report for the sales team so they can see something about orders, thanks a lot."


# ---- checklist ----------------------------------------------------------------------------


def test_full_fs_mentions_every_topic():
    items = checklist.evaluate(FS_FULL)
    missing = [i["id"] for i in items if not i["mentioned"]]
    assert missing == []
    assert checklist.summary(items).startswith("10 of 10")


def test_thin_fs_lists_missing_topics_with_questions():
    items = checklist.evaluate(FS_THIN)
    by = {i["id"]: i for i in items}
    assert by["object_type"]["mentioned"] is True  # the word 'report'
    for k in ("selection", "authorization", "errors", "volume", "testing"):
        assert by[k]["mentioned"] is False, k
    assert all(i["question"].endswith("?") for i in items)


# ---- detection ----------------------------------------------------------------------------


def test_detect_catalog_and_custom_objects():
    d = detect("Read BAPI_PR_CREATE results and table EBAN; program ZMM_OPEN_PR and report YTEST1.")
    assert d["catalog_objects"] == []  # the test KB folder has no catalog
    from pathlib import Path

    from app.catalog.index import Catalog
    from app.catalog.loader import load_dir

    shipped = Catalog(load_dir(Path(__file__).resolve().parents[2] / "knowledge_base" / "catalog"))
    d = detect("Create the requisition with BAPI_PR_CREATE; table EBAN; program ZMM_OPEN_PR and report YTEST1.", shipped)
    names = {o["name"]: o["status"] for o in d["catalog_objects"]}
    assert names.get("BAPI_PR_CREATE") == "unverified"
    assert d["custom_objects"] == ["ZMM_OPEN_PR", "YTEST1"]


def test_detect_ignores_ordinary_words():
    d = detect("ZERO tolerance, YEAR end, Zone check, zmm_lowercase is not an object")
    assert d["custom_objects"] == []


def test_guess_type_is_a_hint_only():
    assert guess_type("An IDoc interface to the warehouse") == "interface"
    assert guess_type("nothing special here") is None


# ---- prompt -------------------------------------------------------------------------------


def test_prompt_rules_and_bounds():
    big = "x " * 20000
    detected = detect(FS_FULL)
    msg = draft_mod.build_user_message(big, detected, ["Authorization - question?"])
    assert "DATA" in draft_mod.SYSTEM and "Do NOT invent" in draft_mod.SYSTEM and "Open questions" in draft_mod.SYSTEM
    assert "Authorization - question?" in msg
    assert len(msg) < draft_mod.LLM_INPUT_CHARS + 3000


# ---- API ----------------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    reset_catalog()
    Base.metadata.drop_all(bind=engine)
    monkeypatch.setattr(draft_mod, "ask_llm", lambda s, m: None)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    reset_catalog()
    get_settings.cache_clear()


def _auth(client, email="sp@example.com"):
    client.post("/auth/register", json={"email": email, "password": "StrongPass123"})
    token = client.post("/auth/login", data={"username": email, "password": "StrongPass123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_requires_login(client):
    assert client.post("/spec/generate", json={"fs_text": FS_FULL}).status_code == 401


def test_without_llm_still_gives_checklist(client):
    r = client.post("/spec/generate", json={"fs_text": FS_THIN}, headers=_auth(client))
    assert r.status_code == 200
    b = r.json()
    assert b["draft"] is None
    assert b["coverage"].startswith("1 of 10") or b["coverage"].startswith("2 of 10")
    assert "not available" in b["note"] and "keywords" in b["note"]
    assert any(not t["mentioned"] for t in b["topics"])


def test_with_llm(client, monkeypatch):
    seen = {}

    def fake(system, message):
        seen["m"] = message
        return "## 1. Purpose\nOpen PR report."

    monkeypatch.setattr(draft_mod, "ask_llm", fake)
    r = client.post("/spec/generate", json={"fs_text": FS_FULL}, headers=_auth(client))
    b = r.json()
    assert b["draft"].startswith("## 1. Purpose")
    assert "can be wrong" in b["note"]
    assert "ZMM_OPEN_PR" in seen["m"]
    assert b["detected"]["custom_objects"] == ["ZMM_OPEN_PR"]


def test_missing_topics_are_passed_to_the_llm(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(draft_mod, "ask_llm", lambda s, m: seen.setdefault("m", m) and "ok")
    client.post("/spec/generate", json={"fs_text": FS_THIN}, headers=_auth(client))
    assert "Authorization" in seen["m"] and "Error handling" in seen["m"]


def test_validates_input(client):
    h = _auth(client)
    assert client.post("/spec/generate", json={"fs_text": "too short"}, headers=h).status_code == 422
    assert client.post("/spec/generate", json={"fs_text": "x" * 15001}, headers=h).status_code == 422
