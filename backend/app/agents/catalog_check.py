"""Phase 3 glue: SAP catalog <-> ABAP agent.

catalog_context()    facts about the SAP objects a question mentions, put in front of the LLM
catalog_fix()        at most ONE LLM round to correct conflicts with the catalog
catalog_note()       short Markdown note under the answer: what was confirmed, what conflicts,
                     what the catalog does not know - always with the entry status

Never raises; with no catalog or no matches nothing is added."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.catalog.checker import Finding, check_blocks
from app.catalog.index import facts_for
from app.catalog.service import get_catalog
from app.config import get_settings
from app.quality.abaplint_check import extract_abap_blocks

log = logging.getLogger(__name__)
AskFn = Callable[[str, str], "str | None"]

MAX_FACT_ENTRIES = 4
STATUS_TAIL = (
    "_Catalog status: `verified` = checked against SAP; `documented` = from a written source; "
    "`unverified` = written from general knowledge and not checked in a system. "
    "Always confirm names in SE37/SE11._"
)


def _enabled() -> bool:
    return get_settings().catalog_enabled


def catalog_context(question: str) -> str:
    if not _enabled():
        return ""
    try:
        entries = get_catalog().search(question, limit=MAX_FACT_ENTRIES)
        if not entries:
            return ""
        return (
            "SAP catalog facts for objects relevant to this question. Use these names and parameter "
            "directions exactly. Entries whose status is 'unverified' are hints written from general "
            "knowledge - mention that when you rely on them. If a list is marked NOT complete, other "
            "parameters or fields may exist; do not invent any that you are not sure of.\n\n"
            f"{facts_for(entries)}\n\n-----\n"
        )
    except Exception:  # noqa: BLE001
        log.warning("Catalog lookup failed", exc_info=True)
        return ""


def _findings(answer: str) -> list[Finding]:
    blocks = extract_abap_blocks(answer)
    if not blocks:
        return []
    return check_blocks(blocks, get_catalog())


def _fix_prompt(question: str, answer: str, conflicts: list[Finding]) -> str:
    entries = {c.subject.split(" ")[0].split("-")[0] for c in conflicts}
    facts = facts_for([e for n in sorted(entries) if (e := get_catalog().get(n))])
    problems = "\n".join(f"- code block {c.block}: {c.message}" for c in conflicts)
    return (
        f"Original question:\n{question}\n\nYour previous answer:\n{answer}\n\n"
        "The ABAP code in your answer conflicts with the SAP catalog:\n"
        f"{problems}\n\nCatalog facts:\n{facts}\n\n"
        "Return the complete corrected answer in the same format (explanation plus code blocks). "
        "Fix only these conflicts. Do not invent parameters, structures or fields. Do not add comments "
        "about this correction."
    )


def catalog_fix(question: str, answer: str, ask: AskFn, system_prompt: str) -> str:
    """One correction round. The corrected answer is used only if it has code and fewer conflicts."""
    if not _enabled():
        return answer
    try:
        conflicts = [f for f in _findings(answer) if f.level == "conflict"]
        if not conflicts:
            return answer
        fixed = ask(system_prompt, _fix_prompt(question, answer, conflicts))
        if not fixed or not extract_abap_blocks(fixed):
            return answer
        remaining = [f for f in _findings(fixed) if f.level == "conflict"]
        return fixed if len(remaining) < len(conflicts) else answer
    except Exception:  # noqa: BLE001
        log.warning("Catalog fix failed", exc_info=True)
        return answer


def catalog_note(answer: str) -> str:
    if not _enabled():
        return ""
    try:
        findings = _findings(answer)
        if not findings:
            return ""
        confirmed = sorted({f"{f.subject.split(' ')[0]} ({f.status})" for f in findings if f.level == "confirmed"})
        conflicts = [f for f in findings if f.level == "conflict"]
        unknown = [f for f in findings if f.level == "unknown"]
        lines = ["", "", "**SAP catalog check**", ""]
        if confirmed:
            lines.append("- Found in catalog: " + ", ".join(confirmed))
        for f in conflicts[:6]:
            lines.append(f"- **Conflict** ({f.status or 'catalog'}): {f.message}")
        if len(conflicts) > 6:
            lines.append(f"- ... and {len(conflicts) - 6} more conflicts")
        if unknown:
            names = sorted({f.subject for f in unknown})
            shown = ", ".join(f"`{n}`" for n in names[:8]) + (f" and {len(names) - 8} more" if len(names) > 8 else "")
            lines.append(f"- Not confirmed by the catalog (it may still be correct): {shown}")
        lines += ["", STATUS_TAIL]
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        log.warning("Catalog note failed", exc_info=True)
        return ""
