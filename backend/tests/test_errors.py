"""Error analyzer: parser, knowledge matching, API."""

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_errors.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.errors import explain as explain_mod  # noqa: E402
from app.errors.loader import ErrorBankError, load_dir  # noqa: E402
from app.errors.parser import parse  # noqa: E402
from app.errors.service import match, reset_entries  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import errors as errors_router  # noqa: E402

SHIPPED = Path(__file__).resolve().parents[2] / "knowledge_base" / "errors"

DUMP = """Runtime Errors         TIME_OUT
Date and Time          15.10.2026 10:22:11

Short text
    Time limit exceeded.

What happened?
    The program "ZMM_REPORT" has exceeded the maximum permitted runtime.

Information on where terminated
    Termination occurred in the ABAP program "ZMM_REPORT" - in "GET_DATA".
    The main program was "ZMM_REPORT ".

    In the source code you have the termination point in line 45
    of the (Include) program "ZMM_REPORT_F01".
"""

ZERO = """Runtime Errors         COMPUTE_INT_ZERODIVIDE
Exception              CX_SY_ZERODIVIDE
Short text
    Division by 0 (type I) in program "ZSD_X".
"""


# ---- parser -------------------------------------------------------------------------------


def test_parse_dump_fields():
    p = parse(DUMP)
    assert p.kind == "dump"
    assert p.runtime_error == "TIME_OUT"
    assert p.short_text == "Time limit exceeded."
    assert p.program == "ZMM_REPORT"
    assert p.include == "ZMM_REPORT_F01"
    assert p.line == 45


def test_parse_exception_class():
    p = parse(ZERO)
    assert p.runtime_error == "COMPUTE_INT_ZERODIVIDE"
    assert p.exception == "CX_SY_ZERODIVIDE"


def test_parse_message_no_forms():
    a = parse("Error: Material 100-100 does not exist in plant 1000. Message no. M3305")
    assert (a.message_class, a.message_number, a.kind) == ("M3", "305", "message")
    b = parse('Message class "MM" Message number 021')
    assert (b.message_class, b.message_number) == ("MM", "021")
    c = parse("Posting period 2026/10 is not open (F5 262)")
    assert (c.message_class, c.message_number) == ("F5", "262")


def test_parse_does_not_invent_fields():
    p = parse("something went wrong when I saved")
    assert p.kind == "text"
    assert p.runtime_error is None and p.program is None and p.line is None and p.message_number is None


def test_parse_transaction_needs_a_real_code():
    assert parse("Transaction was cancelled by the user").transaction is None
    assert parse("Transaction code: MIGO").transaction == "MIGO"


def test_parse_handles_huge_and_empty_input():
    assert parse("").kind == "text"
    parse("x" * 500000)  # must not hang or crash


# ---- knowledge ----------------------------------------------------------------------------


def test_shipped_knowledge_loads_and_is_honest():
    entries = load_dir(SHIPPED)
    assert len(entries) >= 15
    assert len({e.id for e in entries}) == len(entries)
    assert {e.status for e in entries} <= {"verified", "documented", "unverified"}
    for e in entries:
        assert e.causes and e.fix_steps and e.source


def test_matching_ranks_runtime_error_first():
    entries = load_dir(SHIPPED)
    top = match(DUMP, parse(DUMP), entries)
    assert top and top[0].id == "time-out"
    zero = match(ZERO, parse(ZERO), entries)
    assert zero[0].id == "zerodivide"


def test_matching_message_by_phrase():
    entries = load_dir(SHIPPED)
    t = "You are not authorized to use transaction ME21N"
    assert match(t, parse(t), entries)[0].id == "no-authorization"


def test_matching_nothing_gives_empty():
    assert match("hello world", parse("hello world"), load_dir(SHIPPED)) == []


def test_runtime_error_must_be_a_whole_word():
    entries = load_dir(SHIPPED)
    t = "see MY_TIME_OUT_HANDLER for details"
    assert all(e.id != "time-out" for e in match(t, parse(t), entries))


def test_loader_rejects_bad_files(tmp_path):
    (tmp_path / "a.yaml").write_text("- id: x1\n  title: Something\n  causes: [a]\n  fix_steps: [b]\n  source: s1x\n")
    with pytest.raises(ErrorBankError, match="at least one of"):
        load_dir(tmp_path)
    (tmp_path / "a.yaml").write_text("not: a list\n")
    with pytest.raises(ErrorBankError, match="list of entries"):
        load_dir(tmp_path)
    ok = "- id: dup1\n  title: Some title\n  phrases: [boom]\n  causes: [a]\n  fix_steps: [b]\n  source: srcx\n"
    (tmp_path / "a.yaml").write_text(ok)
    (tmp_path / "b.yaml").write_text(ok)
    with pytest.raises(ErrorBankError, match="already used"):
        load_dir(tmp_path)


# ---- LLM prompt ---------------------------------------------------------------------------


def test_prompt_treats_pasted_text_as_data_and_is_bounded():
    big = "Runtime Errors TIME_OUT\n" + "A" * 50000
    msg = explain_mod.build_user_message(big[:20000], parse(big), [])
    assert "DATA" in explain_mod.SYSTEM and "Do not invent" in explain_mod.SYSTEM
    assert len(msg) < explain_mod.LLM_INPUT_CHARS + 2000
    assert "runtime_error: TIME_OUT" in msg


# ---- API ----------------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ERRORS_DIR", str(SHIPPED))
    from app.config import get_settings

    get_settings.cache_clear()
    reset_entries()
    Base.metadata.drop_all(bind=engine)
    monkeypatch.setattr(errors_router.explain_mod, "ask_llm", lambda s, m: None)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    reset_entries()
    get_settings.cache_clear()


def _auth(client, email="er@example.com"):
    client.post("/auth/register", json={"email": email, "password": "StrongPass123"})
    token = client.post("/auth/login", data={"username": email, "password": "StrongPass123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_analyze_requires_login(client):
    assert client.post("/errors/analyze", json={"text": DUMP}).status_code == 401


def test_analyze_without_llm_still_useful(client):
    h = _auth(client)
    r = client.post("/errors/analyze", json={"text": DUMP}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["parsed"]["runtime_error"] == "TIME_OUT" and body["parsed"]["line"] == 45
    assert body["matches"][0]["id"] == "time-out"
    assert "ST22" in body["matches"][0]["tcodes"]
    assert body["explanation"] is None
    assert "not available" in body["note"] and "not yet verified" in body["note"]


def test_analyze_with_llm(client, monkeypatch):
    monkeypatch.setattr(errors_router.explain_mod, "ask_llm", lambda s, m: "## What happened\nIt timed out.")
    r = client.post("/errors/analyze", json={"text": DUMP}, headers=_auth(client))
    assert r.json()["explanation"].startswith("## What happened")
    assert "can be wrong" in r.json()["note"]


def test_analyze_unknown_text(client):
    r = client.post("/errors/analyze", json={"text": "my sap is slow today please help"}, headers=_auth(client))
    assert r.status_code == 200 and r.json()["matches"] == []
    assert "No entry" in r.json()["note"]


def test_analyze_validates_input(client):
    h = _auth(client)
    assert client.post("/errors/analyze", json={"text": ""}, headers=h).status_code == 422
    assert client.post("/errors/analyze", json={"text": "x" * 20001}, headers=h).status_code == 422


def test_coverage(client):
    r = client.get("/errors/coverage", headers=_auth(client))
    assert r.json()["entries"] >= 15 and "TIME_OUT" in r.json()["runtime_errors"]
