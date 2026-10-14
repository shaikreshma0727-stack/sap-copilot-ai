"""Check the SAP names used in ABAP code against the catalog.

Two kinds of findings:
  conflict  the catalog knows the object and the code contradicts it - an unknown parameter or field
            of an entry marked complete, or a parameter given in the wrong section
  unknown   the catalog does not know the name, or knows the object but not that parameter/field
            (its list is incomplete). This is NOT an error: the catalog is small. It is only reported.

Only conflicts make the agent ask the LLM for a fix. The status of the entry a finding is based on
(verified / documented / unverified) is carried along so the note can say how far to trust it."""

from __future__ import annotations

from dataclasses import dataclass

from app.catalog.abap_scan import scan
from app.catalog.index import Catalog
from app.catalog.models import Entry

_SECTION_WORD = {"import": "EXPORTING", "export": "IMPORTING", "tables": "TABLES", "changing": "CHANGING"}
_PHRASE = {
    "import": "an input parameter",
    "export": "an output parameter",
    "tables": "a TABLES parameter",
    "changing": "a CHANGING parameter",
}


@dataclass(frozen=True)
class Finding:
    level: str  # "conflict" | "unknown" | "confirmed"
    block: int
    subject: str  # e.g. BAPI_PR_CREATE or BAPIRET2-MSG
    message: str
    status: str = ""  # status of the catalog entry used


def _resolve_type(var: str, scan_result, catalog: Catalog) -> Entry | None:
    type_name = scan_result.var_types.get(var)
    if type_name is None:
        return None
    if type_name.startswith("@"):  # work area of a loop over a table
        line = scan_result.table_vars.get(type_name[1:])
        type_name = line or ""
        if not type_name:
            return None
    entry = catalog.get(type_name)
    if entry and entry.kind == "table_type":
        return None  # a table, not a structure: components belong to its rows
    if entry and entry.kind in ("structure", "table"):
        return entry
    return None


def check_code(code: str, catalog: Catalog, block: int = 1) -> list[Finding]:
    s = scan(code)
    findings: list[Finding] = []

    # variables whose type we only learn from the function module they receive data from
    for call in s.calls:
        fm = catalog.get(call.name)
        if not fm or fm.kind != "function_module":
            continue
        for section, pname in call.params:
            p = fm.param(pname)
            var = call.values.get(pname)
            if p and var and var not in s.var_types and var not in s.table_vars and p.type:
                t = catalog.get(p.type)
                if t and t.kind == "table_type":
                    s.table_vars[var] = t.line_type
                elif t:
                    s.var_types[var] = p.type

    # resolve table types declared as TYPE bapiret2_t
    for var, type_name in list(s.var_types.items()):
        t = catalog.get(type_name)
        if t and t.kind == "table_type":
            s.table_vars[var] = t.line_type
            del s.var_types[var]
    for var, type_name in list(s.table_vars.items()):
        t = catalog.get(type_name)
        if t and t.kind == "table_type":
            s.table_vars[var] = t.line_type

    seen: set[tuple[str, str, str]] = set()

    def add(level, subject, message, status=""):
        key = (level, subject, message)
        if key not in seen:
            seen.add(key)
            findings.append(Finding(level, block, subject, message, status))

    # 1. CALL FUNCTION
    for call in s.calls:
        fm = catalog.get(call.name)
        if fm is None:
            add("unknown", call.name, f"function module {call.name} is not in the catalog, so its name and parameters could not be checked")
            continue
        if fm.kind != "function_module":
            add("conflict", call.name, f"{call.name} is a {fm.kind.replace('_', ' ')} in the catalog, not a function module", fm.status)
            continue
        add("confirmed", call.name, f"function module {call.name} found in the catalog", fm.status)
        for section, pname in call.params:
            p = fm.param(pname)
            subject = f"{call.name} parameter {pname}"
            if p is None:
                if fm.complete:
                    add("conflict", subject, f"{pname} is not a parameter of {call.name} (the catalog list is complete)", fm.status)
                else:
                    add("unknown", subject, f"{pname} is not in the catalog's (incomplete) parameter list of {call.name}", fm.status)
            elif p.direction != section:
                add(
                    "conflict",
                    subject,
                    f"{pname} is {_PHRASE[p.direction]} of {call.name}; in CALL FUNCTION it must be under "
                    f"{_SECTION_WORD[p.direction]}, not {_SECTION_WORD[section]}",
                    fm.status,
                )

    # 2. structure components (ls_return-message)
    for var, fname in s.component_refs:
        entry = _resolve_type(var, s, catalog)
        if entry is None:
            continue
        subject = f"{entry.name}-{fname}"
        if entry.has_field(fname):
            continue
        if entry.complete:
            add("conflict", subject, f"{fname} is not a field of {entry.name} (the catalog list is complete; variable {var})", entry.status)
        elif entry.fields:
            add("unknown", subject, f"{fname} is not in the catalog's (incomplete) field list of {entry.name}", entry.status)

    # 3. SELECT field lists
    for table, fields in s.selects:
        entry = catalog.get(table)
        if entry is None or entry.kind not in ("table", "structure") or not entry.fields:
            continue
        for fname in fields:
            if entry.has_field(fname):
                continue
            subject = f"{entry.name}-{fname}"
            if entry.complete:
                add("conflict", subject, f"{fname} is not a field of table {entry.name} (the catalog list is complete)", entry.status)
            else:
                add("unknown", subject, f"{fname} is not in the catalog's (incomplete) field list of table {entry.name}", entry.status)
    return findings


def check_blocks(blocks: list[str], catalog: Catalog) -> list[Finding]:
    out: list[Finding] = []
    for i, code in enumerate(blocks, 1):
        out.extend(check_code(code, catalog, i))
    return out
