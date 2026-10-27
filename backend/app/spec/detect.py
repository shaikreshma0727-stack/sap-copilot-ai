"""SAP object names found in the FS text. Nothing is guessed."""
from __future__ import annotations

import re

from app.catalog.index import Catalog
from app.catalog.service import get_catalog

_CUSTOM = re.compile(r"(?<![A-Za-z0-9_/])([ZY][A-Z0-9_]{2,29})(?![A-Za-z0-9_])")
_NOT_OBJECTS = {"YEAR", "YEARS", "YES", "ZERO", "ZIP", "ZONE", "ZONES"}
_KINDS = [
    ("interface", r"\b(interface|idoc|odata|rfc|api)\b"),
    ("enhancement", r"\b(enhancement|user[- ]exit|badi|customer exit|bte)\b"),
    ("form", r"\b(smartform|adobe form|form output|sapscript|print form)\b"),
    ("conversion / upload", r"\b(conversion|migration|upload|bdc|batch input|lsmw)\b"),
    ("report", r"\b(report|alv|list|selection screen)\b"),
]


def guess_type(text: str) -> str | None:
    """First matching kind in a fixed priority order, or None. It is a hint, not a decision."""
    for name, pat in _KINDS:
        if re.search(pat, text, re.I):
            return name
    return None


def detect(text: str, catalog: Catalog | None = None) -> dict:
    cat = get_catalog() if catalog is None else catalog
    known = [
        {"name": e.name, "kind": e.kind, "status": e.status, "description": e.description}
        for e in cat.mentioned(text)
    ]
    seen, custom = set(), []
    for m in _CUSTOM.findall(text):
        # Only upper-case names count: 'Zone' or 'Year' in normal prose must not look like a custom object.
        if m not in seen and m not in _NOT_OBJECTS:
            seen.add(m)
            custom.append(m)
    return {"type_hint": guess_type(text), "catalog_objects": known, "custom_objects": custom}
