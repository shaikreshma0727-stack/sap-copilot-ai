"""Glue between the agents and the knowledge base (Phase 2 -> agents).

retrieve()          finds relevant chunks for a question (never raises: if the knowledge
                    base is empty or the embedding model cannot load, the agent just
                    answers without it).
build_prompt()      puts the numbered excerpts in front of the question.
sources_footer()    Markdown list of the excerpts the answer actually cites.
"""

from __future__ import annotations

import logging
import re

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_HITS = 4
MAX_CHARS_PER_HIT = 1400


def retrieve(question: str, k: int = MAX_HITS) -> list:
    settings = get_settings()
    if not settings.rag_enabled:
        return []
    try:
        from app.rag.service import get_retriever

        return get_retriever().search(question, k=k, mode="hybrid")
    except Exception:  # noqa: BLE001 - the chat must keep working without the KB
        log.warning("Knowledge base search failed; answering without it", exc_info=True)
        return []


def build_prompt(question: str, hits: list) -> str:
    if not hits:
        return question
    blocks = []
    for i, h in enumerate(hits, 1):
        m = h.metadata
        label = m.get("object_name") or m.get("path", "")
        text = h.text if len(h.text) <= MAX_CHARS_PER_HIT else h.text[:MAX_CHARS_PER_HIT] + " ..."
        blocks.append(f"[{i}] {label} (file: {m.get('path', '?')}, source: {m.get('source', '?')})\n{text}")
    context = "\n\n".join(blocks)
    return (
        "Knowledge base excerpts (may or may not be relevant):\n\n"
        f"{context}\n\n"
        "-----\n"
        "Instructions for using the excerpts:\n"
        "- Use an excerpt only if it really helps answer the question, and cite it like [1] or [2]. "
        "Do not cite an excerpt you did not use.\n"
        "- If the excerpts do not cover the question (for example a specific BAPI or table that "
        "is not in them), begin your answer with one sentence saying the knowledge base has nothing "
        "on this and that the rest comes from general SAP knowledge.\n"
        "- Never invent BAPI parameters, structure/type names or field names. If you are not sure of "
        "an exact name, say so and tell the user to check it in SE37/SE11.\n"
        "- Never invent a citation.\n\n"
        f"Question: {question}"
    )


_CITATION = re.compile(r"[\[\u3010](\d{1,2})[\]\u3011]")  # [2] and the full-width variant the LLM sometimes uses


def cited_indices(answer: str, n: int) -> list[int]:
    found = {int(m) for m in _CITATION.findall(answer)}
    return sorted(i for i in found if 1 <= i <= n)


def sources_footer(hits: list, answer: str = "") -> str:
    """List only the excerpts the answer actually cites. If it cites none, say so, so a
    retrieved-but-unused excerpt is never presented as a source."""
    if not hits:
        return ""
    cited = cited_indices(answer, len(hits))
    if not cited:
        return (
            "\n\n---\n_No knowledge-base excerpt was used for this answer. "
            "Verify BAPI, table and field names in SE37/SE11 before relying on the code._"
        )
    lines = []
    seen: set[tuple[str, str]] = set()
    for i in cited:
        m = hits[i - 1].metadata
        key = (m.get("path", ""), m.get("object_name", ""))
        if key in seen:
            continue
        seen.add(key)
        name = m.get("object_name") or m.get("path", "")
        lines.append(f"- [{i}] {name} - `{m.get('path', '?')}` ({m.get('source', '?')})")
    return "\n\n---\n**Knowledge base sources cited**\n\n" + "\n".join(lines)
