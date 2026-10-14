"""Phase 4: check the ABAP code in an answer with abaplint, let the LLM fix what is found,
and add a short status note under the answer.

check_and_fix() never raises and never makes an answer worse: if abaplint is missing, or the
LLM call for a fix fails, the original answer is returned unchanged."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.config import get_settings
from app.quality.abaplint_check import Issue, check_blocks, extract_abap_blocks

AskFn = Callable[[str, str], "str | None"]

NOTE_TAIL = (
    "_This is not a correctness check. abaplint does not know your SAP data dictionary, so it cannot "
    "verify that BAPIs, structures, types or fields exist, or that the logic is right. Verify names in "
    "SE37/SE11 and test in a sandbox system before using the code._"
)


def hints_for(issue: Issue) -> list[str]:
    """Short, targeted reminders for the mistakes LLMs make most often."""
    text = (issue.statement or issue.code_line).lstrip().upper()
    hints = []
    if text.startswith("CALL FUNCTION"):
        hints.append(
            "CALL FUNCTION: write the parameter sections in this order - EXPORTING, IMPORTING, TABLES, "
            "CHANGING, EXCEPTIONS. Do not use '@' in CALL FUNCTION (write IMPORTING p = DATA(var), not "
            "@DATA(var)). A TABLES parameter must be an internal table declared earlier - not VALUE #( ... ) "
            "and not an inline expression."
        )
    if re.match(r"DATA\(\w+\)\s+TYPE\b", text, re.IGNORECASE):
        hints.append("Inline DATA(var) cannot have TYPE. Use DATA var TYPE ... or DATA(var) = value.")
    return hints


def _indent(text: str) -> str:
    return "\n".join("    " + ln for ln in text.splitlines())


def _fix_prompt(question: str, answer: str, issues: list[Issue]) -> str:
    lines = []
    for i in issues:
        where = f"code block {i.block}, line {i.line}"
        if i.statement and "\n" in i.statement:
            lines.append(f"- {where}: {i.message}\n  The statement that does not parse:\n{_indent(i.statement)}")
        else:
            shown = f" -> `{i.code_line}`" if i.code_line else ""
            lines.append(f"- {where}: {i.message}{shown}")
        for hint in hints_for(i):
            lines.append(f"  Hint: {hint}")
    problems = "\n".join(lines)
    return (
        f"Original question:\n{question}\n\n"
        f"Your previous answer:\n{answer}\n\n"
        "The ABAP syntax checker (abaplint) reported these problems in your code:\n"
        f"{problems}\n\n"
        "Return the complete corrected answer in the same format (explanation plus code blocks). "
        "Fix these problems and keep everything else the same. Remember: inline declarations are "
        "written DATA(var) = expr or INTO @DATA(var), never DATA(var) TYPE ... ; do not invent "
        "BAPI parameters, types or field names; do not add comments about this correction."
    )


def _note(issues: list[Issue], blocks: int, fixes: int) -> str:
    if not issues:
        fixed = f" after {fixes} automatic fix{'es' if fixes != 1 else ''}" if fixes else ""
        return f"\n\n**Syntax check (abaplint): no grammar or declaration errors found**{fixed} in {blocks} code block{'s' if blocks != 1 else ''}.\n\n{NOTE_TAIL}"
    shown = issues[:6]
    items = "\n".join(f"- block {i.block}, line {i.line}: {i.message}" for i in shown)
    more = f"\n- ... and {len(issues) - len(shown)} more" if len(issues) > len(shown) else ""
    return (
        f"\n\n**Syntax check (abaplint): {len(issues)} issue{'s' if len(issues) != 1 else ''} still reported"
        f"** - fix these before using the code:\n\n{items}{more}\n\n{NOTE_TAIL}"
    )


def check_and_fix(
    question: str,
    answer: str,
    ask: AskFn,
    system_prompt: str,
    *,
    checker=None,
    max_fixes: int | None = None,
) -> tuple[str, str]:
    """Returns (possibly corrected answer, status note to append - '' when nothing was checked)."""
    checker = checker or check_blocks  # looked up at call time so tests can replace it
    settings = get_settings()
    if not settings.abaplint_enabled:
        return answer, ""
    limit = settings.abaplint_max_fixes if max_fixes is None else max_fixes
    try:
        blocks = extract_abap_blocks(answer)
        if not blocks:
            return answer, ""
        issues = checker(blocks)
        if issues is None:  # abaplint not installed
            return answer, ""
        fixes = 0
        while issues and fixes < limit:
            fixed = ask(system_prompt, _fix_prompt(question, answer, issues))
            if not fixed:
                break
            new_blocks = extract_abap_blocks(fixed)
            if not new_blocks:
                break  # the LLM answered without code; keep the previous answer
            new_issues = checker(new_blocks)
            if new_issues is None:
                break
            fixes += 1
            answer, blocks, issues = fixed, new_blocks, new_issues
        return answer, _note(issues, len(blocks), fixes)
    except Exception:  # noqa: BLE001 - the chat must keep working
        return answer, ""
