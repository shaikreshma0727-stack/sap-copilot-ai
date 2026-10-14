"""Phase 4: abaplint checker + fix loop.

Tests that run the real abaplint are skipped when it is not installed
(cd backend/tools/abaplint && npm install)."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_lint.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402

from app.agents import graph as graph_mod  # noqa: E402
from app.agents.code_check import check_and_fix  # noqa: E402
from app.quality import abaplint_check as ac  # noqa: E402
from app.quality.abaplint_check import Issue, check_blocks, extract_abap_blocks, is_checkable, is_full_unit  # noqa: E402

needs_abaplint = pytest.mark.skipif(not ac.is_available(), reason="abaplint not installed")

BAD = "DATA(lv_carrid) TYPE string.\nWRITE lv_carrid."
GOOD = "DATA(lv_carrid) = `LH`.\nWRITE lv_carrid."


def fenced(code: str) -> str:
    return f"Explanation.\n\n```abap\n{code}\n```\n"


# ---- pure helpers --------------------------------------------------------------------------


def test_extract_blocks_only_abap_fences():
    md = "a\n```abap\nWRITE 1.\n```\nb\n```python\nprint(1)\n```\n```ABAP\nWRITE 2.\n```"
    assert extract_abap_blocks(md) == ["WRITE 1.", "WRITE 2."]


def test_full_unit_and_checkable_detection():
    assert is_full_unit("REPORT zx.\nWRITE 1.")
    assert is_full_unit("CLASS zcl_a DEFINITION PUBLIC.\nENDCLASS.")
    assert not is_full_unit("SELECT SINGLE * FROM t000 INTO @DATA(ls).")
    assert not is_checkable("METHOD m.\n  WRITE 1.\nENDMETHOD.")  # method body alone
    assert not is_checkable("SELECT * FROM t000\n...\nENDSELECT.")  # placeholder
    assert is_checkable("WRITE 1.")


def test_unknown_sap_objects_are_filtered_but_real_errors_kept():
    raw = [
        {"key": "check_syntax", "file": "/x/src/zblk1.prog.abap", "description": 'Class cl_foo not found', "start": {"row": 2}},
        {"key": "check_syntax", "file": "/x/src/zblk1.prog.abap", "description": 'Database table or view "zt" not found', "start": {"row": 3}},
        {"key": "check_syntax", "file": "/x/src/zblk1.prog.abap", "description": '"lv_x" not found, findTop', "start": {"row": 4}},
        {"key": "check_syntax", "file": "/x/src/zblk1.prog.abap", "description": "CATCH, unknown class CX_SY_CONVERSION_ERROR", "start": {"row": 5}},
        {"key": "parser_error", "file": "/x/src/zblk1.prog.abap", "description": "Statement does not exist", "start": {"row": 1}},
        {"key": "unknown_types", "file": "/x/src/zblk1.prog.abap", "description": "ignored rule", "start": {"row": 1}},
    ]
    code = "REPORT zx.\nCL_FOO=>X( ).\nSELECT * FROM zt INTO TABLE @DATA(t).\nWRITE lv_x.\nCATCH cx_x."
    issues = check_blocks([code], runner=lambda files: raw)
    assert [(i.line, i.rule) for i in issues] == [(1, "parser_error"), (4, "check_syntax")]
    assert issues[1].code_line == "WRITE lv_x."


def test_declaration_errors_ignored_for_loose_snippets():
    raw = [{"key": "check_syntax", "file": "x/zblk1.prog.abap", "description": '"lt_itab" not found, findTop', "start": {"row": 1}}]
    assert check_blocks(["READ TABLE lt_itab INDEX 1 INTO DATA(ls)."], runner=lambda f: raw) == []


def test_returns_none_when_checker_unavailable():
    assert check_blocks(["WRITE 1."], runner=lambda files: None) is None


# ---- real abaplint -------------------------------------------------------------------------


@needs_abaplint
def test_real_abaplint_catches_invalid_inline_declaration():
    issues = check_blocks([BAD])
    assert issues and issues[0].rule == "parser_error" and issues[0].line == 1


@needs_abaplint
def test_real_abaplint_accepts_valid_code_and_finds_undeclared_variable():
    assert check_blocks([GOOD]) == []
    issues = check_blocks(["REPORT zx.\nDATA(a) = 1.\nWRITE: / a, lv_missing."])
    assert any(i.rule == "check_syntax" and "lv_missing" in i.message for i in issues)


@needs_abaplint
def test_real_abaplint_ignores_unknown_sap_classes():
    code = "REPORT zx.\nDATA lv_rc TYPE i.\nDATA lt TYPE filetable.\ncl_gui_frontend_services=>file_open_dialog( CHANGING file_table = lt rc = lv_rc )."
    assert check_blocks([code]) == []


# ---- fix loop ------------------------------------------------------------------------------


def fake_checker(blocks):
    issues = []
    for n, code in enumerate(blocks, 1):
        if "TYPE string" in code and "DATA(" in code:
            issues.append(Issue(block=n, line=1, rule="parser_error", message="Statement does not exist", code_line="DATA(x) TYPE string."))
    return issues


def test_loop_fixes_answer_and_reports_pass():
    calls = []

    def ask(system, message):
        calls.append(message)
        return fenced(GOOD)

    answer, note = check_and_fix("q", fenced(BAD), ask, "sys", checker=fake_checker, max_fixes=2)
    assert "DATA(lv_carrid) = `LH`" in answer
    assert len(calls) == 1 and "code block 1, line 1" in calls[0]
    assert "no grammar or declaration errors found" in note and "1 automatic fix" in note


def test_loop_gives_up_after_max_fixes_and_lists_remaining_issues():
    calls = []

    def ask(system, message):
        calls.append(1)
        return fenced(BAD)

    answer, note = check_and_fix("q", fenced(BAD), ask, "sys", checker=fake_checker, max_fixes=2)
    assert len(calls) == 2
    assert "1 issue still reported" in note and "block 1, line 1" in note


def test_llm_failure_keeps_original_answer():
    original = fenced(BAD)
    answer, note = check_and_fix("q", original, lambda s, m: None, "sys", checker=fake_checker, max_fixes=2)
    assert answer == original and "still reported" in note


def test_no_code_or_no_checker_means_no_note_and_no_change():
    assert check_and_fix("q", "plain text", lambda s, m: "x", "s", checker=fake_checker) == ("plain text", "")
    original = fenced(BAD)
    assert check_and_fix("q", original, lambda s, m: "x", "s", checker=lambda b: None) == (original, "")


def test_can_be_switched_off(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "abaplint_enabled", False)
    original = fenced(BAD)
    assert check_and_fix("q", original, lambda s, m: "x", "s", checker=fake_checker) == (original, "")


# ---- wired into the agent ------------------------------------------------------------------


def test_abap_agent_runs_the_check_but_functional_agent_does_not(monkeypatch):
    seen = []

    def fake_llm(system, message):
        seen.append(message)
        return fenced(BAD) if len(seen) == 1 else fenced(GOOD)

    monkeypatch.setattr(graph_mod, "ask_llm", fake_llm)
    monkeypatch.setattr(graph_mod, "retrieve", lambda q: [])
    monkeypatch.setattr("app.agents.code_check.check_blocks", fake_checker)
    monkeypatch.setattr(graph_mod, "route", lambda m: "abap")
    graph_mod.build_graph.cache_clear()
    out = graph_mod.run_copilot("write code")
    assert "DATA(lv_carrid) = `LH`" in out["answer"] and "no grammar or declaration errors found" in out["answer"]

    seen.clear()
    monkeypatch.setattr(graph_mod, "route", lambda m: "functional")
    graph_mod.build_graph.cache_clear()
    out = graph_mod.run_copilot("explain P2P")
    assert "Syntax check" not in out["answer"] and len(seen) == 1
    graph_mod.build_graph.cache_clear()


@needs_abaplint
def test_real_abaplint_catches_inline_declaration_in_changing():
    code = "REPORT zx.\ncl_gui_frontend_services=>file_open_dialog( CHANGING file_table = DATA(lt) rc = DATA(rc) )."
    issues = check_blocks([code])
    assert any("inlined" in i.message for i in issues)
