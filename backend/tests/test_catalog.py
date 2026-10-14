"""Phase 3: SAP catalog - loader, index, scanner, checker, agent glue, API."""

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_catalog.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents import catalog_check as cc  # noqa: E402
from app.agents import graph as graph_mod  # noqa: E402
from app.catalog.abap_scan import scan, split_statements, strip_comments  # noqa: E402
from app.catalog.checker import check_code  # noqa: E402
from app.catalog.index import Catalog, facts_for  # noqa: E402
from app.catalog.loader import CatalogError, load_dir  # noqa: E402
from app.catalog.service import reset_catalog  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

SEED = Path(__file__).resolve().parents[2] / "knowledge_base" / "catalog"


@pytest.fixture(scope="module")
def catalog():
    return Catalog(load_dir(SEED))


def fenced(code: str) -> str:
    return f"Explanation.\n\n```abap\n{code}\n```\n"


# ---- loader --------------------------------------------------------------------------------


def test_seed_files_load_and_are_all_honestly_unverified(catalog):
    assert len(catalog) >= 10
    assert catalog.get("bapiret2").complete
    assert {e.status for e in catalog.entries} == {"unverified"}  # nothing claims to be checked


def test_verified_needs_a_source(tmp_path):
    (tmp_path / "a.yaml").write_text("- {name: X_Y, kind: table, status: verified}\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="needs a 'source'"):
        load_dir(tmp_path)


@pytest.mark.parametrize(
    "text, message",
    [
        ("- {name: A, kind: table}\n- {name: a, kind: table}\n", "already defined"),
        ("- {name: A, kind: function_module, fields: [X]}\n", "has 'params'"),
        ("- {name: A, kind: wrong}\n", "kind"),
        ("{not: a list}\n", "list of entries"),
        ("- [unclosed\n", "not valid YAML"),
    ],
)
def test_bad_files_give_clear_errors(tmp_path, text, message):
    (tmp_path / "a.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(CatalogError, match=message):
        load_dir(tmp_path)


def test_missing_folder_is_an_empty_catalog(tmp_path):
    assert load_dir(tmp_path / "nope") == []


# ---- index ---------------------------------------------------------------------------------


def test_search_by_name_and_keyword(catalog):
    assert catalog.search("how do I use BAPI_PR_CREATE?")[0].name == "BAPI_PR_CREATE"
    assert "BAPI_PR_CREATE" in [e.name for e in catalog.search("create a purchase requisition from a file")]
    assert catalog.search("what is a closure in python") == []


def test_facts_show_status_and_completeness(catalog):
    text = facts_for([catalog.get("BAPI_PR_CREATE"), catalog.get("BAPIRET2")])
    assert "status: unverified" in text and "list is NOT complete" in text and "list is complete" in text
    assert "import PRHEADER" in text and "tables PRITEM" in text


# ---- scanner -------------------------------------------------------------------------------


def test_scanner_ignores_comments_and_strings():
    code = "* CALL FUNCTION 'FAKE'.\nWRITE 'a.b'. \" CALL FUNCTION 'X2'.\nWRITE 2."
    assert split_statements(code) == ["WRITE 'a.b'.", "WRITE 2."]
    assert "FAKE" not in strip_comments(code)


def test_scanner_reads_call_function_sections_and_ignores_nested_names():
    s = scan(
        "CALL FUNCTION 'ZFM'\n EXPORTING a = VALUE #( b = 1 ) c = 2\n IMPORTING d = DATA(lv)\n"
        " TABLES t = lt\n EXCEPTIONS error = 1 OTHERS = 2."
    )
    call = s.calls[0]
    assert call.name == "ZFM"
    assert call.params == [("import", "A"), ("import", "C"), ("export", "D"), ("tables", "T")]
    assert call.values["D"] == "lv"


# ---- checker -------------------------------------------------------------------------------


def _levels(findings):
    return [(f.level, f.subject) for f in findings if f.level != "confirmed"]


def test_unknown_field_of_complete_structure_is_a_conflict(catalog):
    code = "DATA ls_return TYPE bapiret2.\nWRITE ls_return-message_text.\nWRITE ls_return-message."
    assert _levels(check_code(code, catalog)) == [("conflict", "BAPIRET2-MESSAGE_TEXT")]


def test_work_area_of_loop_over_table_type_is_resolved(catalog):
    code = "DATA lt TYPE bapiret2_t.\nLOOP AT lt INTO DATA(ls).\n  WRITE ls-msg.\nENDLOOP."
    assert _levels(check_code(code, catalog)) == [("conflict", "BAPIRET2-MSG")]
    code = "DATA lt TYPE STANDARD TABLE OF bapiret2.\nLOOP AT lt ASSIGNING FIELD-SYMBOL(<r>).\n  WRITE <r>-type.\nENDLOOP."
    assert _levels(check_code(code, catalog)) == []


def test_parameter_in_wrong_section_is_a_conflict(catalog):
    code = "CALL FUNCTION 'BAPI_PR_CREATE'\n EXPORTING prheader = ls_h return = lt_r\n TABLES pritem = lt_i."
    out = check_code(code, catalog)
    assert ("conflict", "BAPI_PR_CREATE parameter RETURN") in _levels(out)
    assert not any(f.subject.endswith("PRHEADER") or f.subject.endswith("PRITEM") for f in out if f.level != "confirmed")


def test_incomplete_entries_report_unknown_not_conflict(catalog):
    code = "CALL FUNCTION 'BAPI_PR_CREATE' EXPORTING foo = 1.\nSELECT banfn, bogus FROM eban INTO TABLE @DATA(lt)."
    assert _levels(check_code(code, catalog)) == [("unknown", "BAPI_PR_CREATE parameter FOO"), ("unknown", "EBAN-BOGUS")]


def test_unknown_function_module_is_only_reported(catalog):
    out = check_code("CALL FUNCTION 'Z_MY_FM' EXPORTING x = 1.", catalog)
    assert _levels(out) == [("unknown", "Z_MY_FM")]


def test_type_is_inferred_from_importing_parameter(catalog):
    code = "CALL FUNCTION 'BAPI_TRANSACTION_COMMIT' EXPORTING wait = 'X' IMPORTING return = DATA(ls_r).\nWRITE ls_r-msg."
    assert ("conflict", "BAPIRET2-MSG") in _levels(check_code(code, catalog))


def test_correct_code_has_no_conflicts(catalog):
    code = (
        "DATA lt_return TYPE bapiret2_t.\nDATA lt_item TYPE STANDARD TABLE OF bapimereqitemimp.\n"
        "CALL FUNCTION 'BAPI_PR_CREATE'\n  EXPORTING prheader = ls_h\n  TABLES return = lt_return pritem = lt_item.\n"
        "CALL FUNCTION 'BAPI_TRANSACTION_COMMIT' EXPORTING wait = 'X'.\n"
        "SELECT banfn, bnfpo, matnr FROM eban INTO TABLE @DATA(lt_e)."
    )
    assert [f for f in check_code(code, catalog) if f.level != "confirmed"] == []


# ---- agent glue ----------------------------------------------------------------------------


@pytest.fixture()
def seeded(catalog, monkeypatch):
    monkeypatch.setattr(cc, "get_catalog", lambda: catalog)


BAD = "DATA ls TYPE bapiret2.\nWRITE ls-message_text."
GOOD = "DATA ls TYPE bapiret2.\nWRITE ls-message."


def test_context_names_the_objects_in_the_question(seeded):
    ctx = cc.catalog_context("Create a purchase requisition with BAPI_PR_CREATE")
    assert "BAPI_PR_CREATE" in ctx and "unverified" in ctx
    assert cc.catalog_context("explain closures") == ""


def test_fix_round_replaces_a_conflicting_answer(seeded):
    asked = []
    out = cc.catalog_fix("q", fenced(BAD), lambda s, m: asked.append(m) or fenced(GOOD), "sys")
    assert "ls-message." in out and len(asked) == 1 and "MESSAGE_TEXT" in asked[0]


def test_fix_round_keeps_original_when_the_fix_is_no_better(seeded):
    assert cc.catalog_fix("q", fenced(BAD), lambda s, m: fenced(BAD), "s") == fenced(BAD)
    assert cc.catalog_fix("q", fenced(BAD), lambda s, m: None, "s") == fenced(BAD)
    assert cc.catalog_fix("q", fenced(BAD), lambda s, m: "no code here", "s") == fenced(BAD)


def test_no_llm_call_when_nothing_conflicts(seeded):
    def boom(s, m):
        raise AssertionError("LLM should not be called")

    assert cc.catalog_fix("q", fenced(GOOD), boom, "s") == fenced(GOOD)


def test_note_lists_confirmed_conflicts_unknowns_and_status(seeded):
    code = "CALL FUNCTION 'BAPI_PR_CREATE' EXPORTING return = x.\nCALL FUNCTION 'Z_X'.\nDATA ls TYPE bapiret2.\nWRITE ls-msg."
    note = cc.catalog_note(fenced(code))
    assert "Found in catalog: BAPI_PR_CREATE (unverified)" in note
    assert "**Conflict**" in note and "Z_X" in note and "not checked in a system" in note
    assert cc.catalog_note("plain text, no code") == ""


def test_can_be_switched_off(seeded, monkeypatch):
    monkeypatch.setattr(cc, "_enabled", lambda: False)
    assert cc.catalog_context("BAPI_PR_CREATE") == ""
    assert cc.catalog_fix("q", fenced(BAD), lambda s, m: fenced(GOOD), "s") == fenced(BAD)
    assert cc.catalog_note(fenced(BAD)) == ""


def test_abap_agent_uses_catalog_end_to_end(seeded, monkeypatch):
    prompts = []

    def fake_llm(system, message):
        prompts.append(message)
        return fenced(BAD) if len(prompts) == 1 else fenced(GOOD)

    monkeypatch.setattr(graph_mod, "ask_llm", fake_llm)
    monkeypatch.setattr(graph_mod, "retrieve", lambda q: [])
    monkeypatch.setattr(graph_mod, "route", lambda m: "abap")
    monkeypatch.setattr("app.agents.code_check.check_blocks", lambda blocks: [])  # abaplint out of the picture
    commit = "\nCALL FUNCTION 'BAPI_TRANSACTION_COMMIT' EXPORTING wait = 'X'."
    monkeypatch.setattr(graph_mod, "ask_llm", lambda s, m: (prompts.append(m), fenced(BAD + commit) if len(prompts) == 1 else fenced(GOOD + commit))[1])
    graph_mod.build_graph.cache_clear()
    out = graph_mod.run_copilot("show a return message from BAPIRET2")
    assert "BAPIRET2" in prompts[0] and "SAP catalog facts" in prompts[0]  # grounding reached the LLM
    assert "ls-message." in out["answer"] and "message_text" not in out["answer"]
    assert "SAP catalog check" in out["answer"]
    graph_mod.build_graph.cache_clear()


# ---- API -----------------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch, catalog):
    monkeypatch.setenv("CATALOG_DIR", str(SEED))
    from app.config import get_settings

    get_settings.cache_clear()
    reset_catalog()
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    reset_catalog()
    get_settings.cache_clear()


def _auth(client):
    client.post("/auth/register", json={"email": "cat@example.com", "password": "StrongPass123"})
    token = client.post("/auth/login", data={"username": "cat@example.com", "password": "StrongPass123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_catalog_api(client):
    assert client.get("/catalog/stats").status_code == 401
    h = _auth(client)
    assert client.get("/catalog/stats", headers=h).json()["total"] >= 10
    r = client.get("/catalog/BAPI_PR_CREATE", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "unverified"
    assert client.get("/catalog/NOPE_NOPE", headers=h).status_code == 404
    hits = client.get("/catalog/search", params={"q": "create purchase requisition"}, headers=h).json()
    assert hits and hits[0]["name"] == "BAPI_PR_CREATE"
