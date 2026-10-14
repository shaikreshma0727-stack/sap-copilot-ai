"""A small ABAP scanner: just enough to find the SAP names a snippet uses.

It is not a parser. It removes comments, splits statements on '.', and pulls out
  - CALL FUNCTION 'NAME' ... with its parameter names per section
  - DATA / TYPES declarations (variable -> type, table -> line type)
  - LOOP AT / READ TABLE ... INTO / ASSIGNING (work area -> line type)
  - structure-component references like ls_return-message
  - SELECT field lists with a single FROM table
Anything it cannot read is skipped, never guessed."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN = re.compile(r"'[^']*'|`[^`]*`|\|[^|]*\||[()=]|[\w<>/~@#-]+|\S")
_SECTIONS = {"EXPORTING": "import", "IMPORTING": "export", "TABLES": "tables", "CHANGING": "changing"}
_STOP_SECTIONS = {"EXCEPTIONS", "DESTINATION", "STARTING", "IN", "AS", "KEEPING", "PERFORMING", "CALLING"}


def strip_comments(code: str) -> str:
    """Remove full-line '*' comments and trailing '"' comments, keeping string literals intact."""
    out = []
    for line in code.splitlines():
        if line.startswith("*"):
            out.append("")
            continue
        quote = None
        cut = len(line)
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in ("'", "`", "|"):
                quote = ch
            elif ch == '"':
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def split_statements(code: str) -> list[str]:
    statements, buf, quote = [], [], None
    for ch in strip_comments(code):
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", "`", "|"):
            quote = ch
            buf.append(ch)
        elif ch == ".":
            buf.append(ch)
            statements.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


@dataclass
class FmCall:
    name: str
    params: list[tuple[str, str]] = field(default_factory=list)  # (section as FM direction, NAME)
    values: dict[str, str] = field(default_factory=dict)  # PARAM -> variable named on the right side


@dataclass
class Scan:
    calls: list[FmCall] = field(default_factory=list)
    var_types: dict[str, str] = field(default_factory=dict)  # variable (lower) -> structure/table-type name
    table_vars: dict[str, str] = field(default_factory=dict)  # internal table (lower) -> line type name
    component_refs: list[tuple[str, str]] = field(default_factory=list)  # (variable lower, FIELD)
    selects: list[tuple[str, list[str]]] = field(default_factory=list)  # (TABLE, [FIELD, ...])


def _parse_call(statement: str) -> FmCall | None:
    m = re.match(r"\s*CALL\s+FUNCTION\s+'([^']+)'(.*)$", statement, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    call = FmCall(name=m.group(1).strip().upper())
    tokens = _TOKEN.findall(m.group(2))
    section, depth, i = None, 0, 0
    while i < len(tokens):
        tok = tokens[i]
        up = tok.upper()
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and up in _SECTIONS:
            section = _SECTIONS[up]
        elif depth == 0 and up in _STOP_SECTIONS | {"EXCEPTIONS"}:
            section = None
        elif depth == 0 and section and i + 1 < len(tokens) and tokens[i + 1] == "=" and re.fullmatch(r"\w+", tok):
            call.params.append((section, up))
            # the value: `x`, `@x`, `DATA(x)`, `@DATA(x)`
            rest = tokens[i + 2 : i + 6]
            joined = "".join(rest[:4])
            vm = re.match(r"@?DATA\((\w+)\)", joined, re.IGNORECASE) or re.match(r"@?(\w+)", joined)
            if vm:
                call.values[up] = vm.group(1).lower()
            i += 1  # skip '='
        i += 1
    return call


_DECL = re.compile(
    r"^\s*(?:DATA|TYPES|STATICS|CONSTANTS)\s*:?\s*(\w+)\s+TYPE\s+(?:(?:STANDARD|SORTED|HASHED)\s+)?(TABLE\s+OF\s+)?(?:REF\s+TO\s+)?(\w+)",
    re.IGNORECASE,
)
_LOOP = re.compile(
    r"^\s*(?:LOOP\s+AT|READ\s+TABLE)\s+(\w+)\b.*?\b(?:INTO|ASSIGNING)\s+(?:FIELD-SYMBOL\s*\(\s*(<\w+>)\s*\)|(?:DATA\s*\(\s*(\w+)\s*\))|(<\w+>)|(\w+))",
    re.IGNORECASE | re.DOTALL,
)
_COMPONENT = re.compile(r"(?<![\w>~-])(<\w+>|[A-Za-z_]\w*)-([A-Za-z_]\w*)\b")
_SELECT = re.compile(r"^\s*SELECT\s+(?:SINGLE\s+|DISTINCT\s+)*(.*?)\s+FROM\s+(\w+)\b(.*)$", re.IGNORECASE | re.DOTALL)


def _select_fields(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("*") or "(" in raw:
        return []
    fields = []
    for part in re.split(r"[,\s]+", raw):
        part = part.strip()
        if not part or part.upper() in {"AS", "FIELDS"}:
            continue
        part = part.split("~")[-1]
        if re.fullmatch(r"[A-Za-z_]\w*", part):
            fields.append(part.upper())
    return fields


def scan(code: str) -> Scan:
    result = Scan()
    for st in split_statements(code):
        call = _parse_call(st)
        if call:
            result.calls.append(call)
            continue
        m = _DECL.match(st)
        if m:
            var, is_table, type_name = m.group(1).lower(), m.group(2), m.group(3).upper()
            if is_table:
                result.table_vars[var] = type_name
            else:
                result.var_types[var] = type_name
        m = _LOOP.match(st)
        if m:
            table = m.group(1).lower()
            work = next((g for g in m.groups()[1:] if g), None)
            if work:
                result.var_types.setdefault(work.lower(), "@" + table)  # "@t" = line type of table t
        sm = _SELECT.match(st)
        if sm and not re.search(r"\bJOIN\b", sm.group(3), re.IGNORECASE):
            fields = _select_fields(sm.group(1))
            if fields:
                result.selects.append((sm.group(2).upper(), fields))
    stripped = strip_comments(code)
    stripped = re.sub(r"'[^']*'|`[^`]*`|\|[^|]*\|", "''", stripped)
    for m in _COMPONENT.finditer(stripped):
        result.component_refs.append((m.group(1).lower(), m.group(2).upper()))
    return result
