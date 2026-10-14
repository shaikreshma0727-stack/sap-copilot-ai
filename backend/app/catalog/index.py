from __future__ import annotations

import re
from collections import Counter

from app.catalog.models import Entry

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_/]{2,}")


class Catalog:
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self._by_name = {e.name: e for e in entries}

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, name: str) -> Entry | None:
        return self._by_name.get(name.strip().upper())

    def mentioned(self, text: str) -> list[Entry]:
        """Entries whose exact name appears as a word in the text (in order of appearance)."""
        found, seen = [], set()
        for word in _WORD.findall(text):
            e = self._by_name.get(word.upper())
            if e and e.name not in seen:
                seen.add(e.name)
                found.append(e)
        return found

    def search(self, text: str, limit: int = 5) -> list[Entry]:
        """Entries named in the text first, then entries whose keywords/description match."""
        result = self.mentioned(text)
        low = text.lower()
        scored = []
        for e in self.entries:
            if e in result:
                continue
            score = sum(2 for k in e.keywords if k in low)
            score += sum(1 for w in set(_WORD.findall(e.description.lower())) if len(w) > 5 and w in low)
            if score >= 2:
                scored.append((score, e.name, e))
        scored.sort(key=lambda t: (-t[0], t[1]))
        result.extend(e for _, _, e in scored)
        return result[:limit]

    def stats(self) -> dict:
        return {
            "total": len(self.entries),
            "by_kind": dict(Counter(e.kind for e in self.entries)),
            "by_status": dict(Counter(e.status for e in self.entries)),
            "complete": sum(1 for e in self.entries if e.complete),
        }


def facts_for(entries: list[Entry]) -> str:
    """Compact text description of entries, for the LLM prompt."""
    lines = []
    for e in entries:
        head = f"- {e.name} [{e.kind.replace('_', ' ')}"
        head += f", {e.module}" if e.module else ""
        head += f", status: {e.status}"
        if e.kind != "table_type":
            head += ", list is complete" if e.complete else ", list is NOT complete"
        lines.append(head + "]" + (f" {e.description}" if e.description else ""))
        if e.params:
            lines.append("  Parameters: " + "; ".join(f"{p.direction} {p.name}" + (f" ({p.type})" if p.type else "") for p in e.params))
        if e.fields:
            lines.append("  Fields: " + ", ".join(f.name + ("*" if f.key else "") for f in e.fields) + ("  (* = key)" if any(f.key for f in e.fields) else ""))
        if e.line_type:
            lines.append(f"  Table type with line type {e.line_type}")
        if e.notes:
            lines.append(f"  Note: {e.notes}")
    return "\n".join(lines)
