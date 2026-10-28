"""Code review mode: rules, API."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_review.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.review import assess as assess_mod  # noqa: E402
from app.review.rules import review, statements  # noqa: E402
from app.routers import review as review_router  # noqa: E402


def rules(code: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for f in review(code):
        out.setdefault(f.rule, []).append(f.line)
    return out


BAD = """REPORT zbad.
DATA: lt_vbak TYPE TABLE OF vbak,
      lt_vbap TYPE TABLE OF vbap,
      ls_vbap TYPE vbap.
SELECT * FROM vbak INTO TABLE lt_vbak.
LOOP AT lt_vbak INTO DATA(ls_vbak).
  SELECT SINGLE * FROM kna1 INTO @DATA(ls_kna1) WHERE kunnr = @ls_vbak-kunnr.
  LOOP AT lt_vbap INTO ls_vbap WHERE vbeln = ls_vbak-vbeln.
    WRITE ls_vbap-posnr.
  ENDLOOP.
  COMMIT WORK.
ENDLOOP.
SELECT matnr FROM mara INTO TABLE @DATA(lt_mara) FOR ALL ENTRIES IN lt_vbap WHERE matnr = lt_vbap-matnr.
BREAK-POINT.
MESSAGE 'Something failed' TYPE 'E'.
"""

GOOD = """REPORT zgood.
DATA lt_vbap TYPE STANDARD TABLE OF vbap WITH DEFAULT KEY.
DATA lv_count TYPE i.
AUTHORITY-CHECK OBJECT 'V_VBAK_VKO' ID 'ACTVT' FIELD '03'.
IF lt_vbap IS NOT INITIAL.
  SELECT matnr, werks FROM marc INTO TABLE @DATA(lt_marc)
    FOR ALL ENTRIES IN @lt_vbap WHERE matnr = @lt_vbap-matnr.
ENDIF.
SELECT SINGLE kunnr FROM kna1 INTO @DATA(lv_kunnr) WHERE land1 = 'IN'.
IF sy-subrc <> 0.
  MESSAGE e001(zmsg).
ENDIF.
lv_count = lv_count + 1.
"""


# ---- rules --------------------------------------------------------------------------------


def test_statements_keep_start_lines_and_ignore_comments_and_strings():
    s = statements("* comment line\nDATA a TYPE i. \" trailing\nWRITE 'a.b.c'.\nIF a = 1.\n  a = 2.\nENDIF.")
    assert [(x.line, x.text) for x in s] == [
        (2, "DATA a TYPE i"), (3, "WRITE 'a.b.c'"), (4, "IF a = 1"), (5, "a = 2"), (6, "ENDIF")]


def test_bad_code_findings_with_lines():
    r = rules(BAD)
    assert r["select-star"] == [5, 7]
    assert r["select-in-loop"] == [7]
    assert r["nested-loop"] == [8]
    assert r["commit-in-loop"] == [11]
    assert r["fae-empty-check"] == [13]
    assert r["breakpoint"] == [14]
    assert r["hardcoded-message"] == [15]
    assert r["no-authority-check"] == [1]
    assert r["no-subrc-select"] == [7]


def test_good_code_is_clean():
    assert rules(GOOD) == {}


def test_fae_guard_forms_are_accepted():
    for guard in ("IF lt_a IS NOT INITIAL.", "IF lines( lt_a ) > 0.", "CHECK lt_a[] IS NOT INITIAL."):
        code = f"{guard}\nSELECT matnr FROM mara INTO TABLE @DATA(lt_m) FOR ALL ENTRIES IN lt_a WHERE matnr = lt_a-matnr.\n"
        assert "fae-empty-check" not in rules(code), guard
    assert "fae-empty-check" in rules("SELECT matnr FROM mara INTO TABLE @DATA(lt_m) FOR ALL ENTRIES IN lt_a WHERE matnr = lt_a-matnr.")


def test_loop_depth_resets_after_endloop():
    code = "LOOP AT lt INTO ls.\nENDLOOP.\nSELECT SINGLE matnr FROM mara INTO @DATA(lv) WHERE matnr = 'X'.\nIF sy-subrc = 0.\nENDIF.\n"
    assert "select-in-loop" not in rules(code)
    assert "nested-loop" not in rules("LOOP AT a INTO x.\nENDLOOP.\nLOOP AT b INTO y.\nENDLOOP.\n")


def test_read_table_checks():
    assert "no-subrc-read" in rules("READ TABLE lt INTO ls WITH KEY a = 1.\nWRITE ls-a.\n")
    assert "no-subrc-read" not in rules("READ TABLE lt INTO ls WITH KEY a = 1.\nIF sy-subrc = 0.\nENDIF.\n")
    assert "no-subrc-read" not in rules("READ TABLE lt ASSIGNING FIELD-SYMBOL(<f>) INDEX 1.\nIF <f> IS ASSIGNED.\nENDIF.\n")
    loop = "LOOP AT a INTO x.\nREAD TABLE b INTO y WITH KEY k = x-k.\nIF sy-subrc = 0.\nENDIF.\nENDLOOP.\n"
    assert "read-in-loop" in rules(loop)
    assert "read-in-loop" not in rules(loop.replace("WITH KEY k = x-k", "WITH KEY k = x-k BINARY SEARCH"))


def test_obsolete_statements():
    r = rules("MOVE a TO b.\nCALL METHOD lo->run.\nADD 1 TO c.\nTABLES mara.\nDATA lt TYPE TABLE OF mara WITH HEADER LINE.\nDATA lt2 TYPE mara OCCURS 0.\nMOVE-CORRESPONDING a TO b.\n")
    for k in ("obsolete-move", "obsolete-call-method", "obsolete-arith", "obsolete-tables", "header-line"):
        assert k in r, k
    assert r["obsolete-move"] == [1]  # MOVE-CORRESPONDING is not flagged by this rule
    assert len(r["header-line"]) == 2


def test_names_that_start_like_keywords_are_not_flagged():
    code = "DATA break_flag TYPE abap_bool.\nbreak_flag = abap_true.\ndo_something( ).\nmoved = 1.\n"
    assert rules(code) == {}


def test_endselect_and_severity_order():
    findings = review(BAD)
    sev = [f.severity for f in findings]
    assert sev == sorted(sev, key=["high", "medium", "low", "info"].index)
    assert "endselect" in rules("SELECT matnr FROM mara INTO @DATA(ls).\nENDSELECT.\n")


# ---- prompt -------------------------------------------------------------------------------


def test_prompt_numbers_lines_and_treats_code_as_data():
    msg = assess_mod.build_user_message("A = 1.\nB = 2.", [{"line": 2, "severity": "low", "title": "T"}], None)
    assert "   2 | B = 2." in msg and "abaplint not available" in msg and "line 2 [low] T" in msg
    assert "DATA" in assess_mod.SYSTEM and "Do NOT claim" in assess_mod.SYSTEM
    assert len(assess_mod.build_user_message("x\n" * 20000, [], [])) < assess_mod.LLM_INPUT_CHARS + 1500


# ---- API ----------------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    monkeypatch.setattr(assess_mod, "ask_llm", lambda s, m: None)
    monkeypatch.setattr(review_router.abaplint_check, "is_available", lambda: False)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


def _auth(client, email="rv@example.com"):
    client.post("/auth/register", json={"email": email, "password": "StrongPass123"})
    token = client.post("/auth/login", data={"username": email, "password": "StrongPass123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_requires_login(client):
    assert client.post("/review/code", json={"code": BAD}).status_code == 401


def test_without_llm_or_abaplint_still_returns_findings(client):
    r = client.post("/review/code", json={"code": BAD}, headers=_auth(client))
    assert r.status_code == 200
    b = r.json()
    assert b["review"] is None and b["syntax_checked"] is False
    assert b["findings"][0]["severity"] == "high"
    assert "not installed" in b["note"] and "not available" in b["note"] and "false positives" in b["note"]


def test_fenced_code_is_unwrapped_and_lines_match(client):
    fenced = "```abap\n" + BAD + "```"
    b = client.post("/review/code", json={"code": fenced}, headers=_auth(client)).json()
    assert {f["line"] for f in b["findings"] if f["rule"] == "breakpoint"} == {14}


def test_with_llm_and_syntax(client, monkeypatch):
    monkeypatch.setattr(review_router.abaplint_check, "is_available", lambda: True)

    class I:
        line, message = 3, "Statement does not match any pattern"

    monkeypatch.setattr(review_router.abaplint_check, "check_blocks", lambda blocks: [I()])
    seen = {}
    monkeypatch.setattr(assess_mod, "ask_llm", lambda s, m: seen.setdefault("m", m) and "## Summary\nok")
    b = client.post("/review/code", json={"code": BAD}, headers=_auth(client)).json()
    assert b["review"].startswith("## Summary") and b["syntax_checked"] is True
    assert b["syntax"] == [{"line": 3, "message": "Statement does not match any pattern"}]
    assert "line 3: Statement does not match" in seen["m"] and "Database SELECT inside a loop" in seen["m"]


def test_validates_input(client):
    h = _auth(client)
    assert client.post("/review/code", json={"code": "x"}, headers=h).status_code == 422
    assert client.post("/review/code", json={"code": "x" * 15001}, headers=h).status_code == 422
