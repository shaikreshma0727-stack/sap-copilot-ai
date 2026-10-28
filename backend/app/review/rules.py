"""Pattern rules over ABAP statements. Pure text analysis, no SAP system involved."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.catalog.abap_scan import strip_comments

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
LOOP_OPEN = {"LOOP", "DO", "WHILE"}
LOOP_CLOSE = {"ENDLOOP", "ENDDO", "ENDWHILE"}


@dataclass
class Stmt:
    line: int  # 1-based line where the statement starts
    text: str  # whitespace-normalised, without the final '.'
    upper: str


@dataclass
class Finding:
    rule: str
    severity: str  # high | medium | low | info
    line: int
    title: str
    why: str
    suggestion: str
    code: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def statements(code: str) -> list[Stmt]:
    """Split on '.' outside string literals, keeping the start line of each statement."""
    text = strip_comments(code)
    out: list[Stmt] = []
    buf: list[str] = []
    quote = None
    line, start = 1, None
    for ch in text:
        if ch == "\n":
            line += 1
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", "`", "|"):
            quote = ch
            if start is None:
                start = line
            buf.append(ch)
        elif ch == ".":
            raw = "".join(buf)
            if raw.strip():
                norm = " ".join(raw.split())
                out.append(Stmt(start or line, norm, norm.upper()))
            buf, start = [], None
        else:
            if start is None and not ch.isspace():
                start = line
            buf.append(ch)
    tail = " ".join("".join(buf).split())
    if tail:
        out.append(Stmt(start or line, tail, tail.upper()))
    return out


def _first(s: Stmt, n: int = 1) -> list[str]:
    return s.upper.split()[:n]


_FAE = re.compile(r"FOR\s+ALL\s+ENTRIES\s+IN\s+@?([\w<>\-\[\]]+)", re.I)
_SELECT_STAR = re.compile(r"^SELECT\s+(SINGLE\s+)?(DISTINCT\s+)?\*", re.I)
_OBSOLETE_ARITH = {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}
_SYSUBRC_NEAR = re.compile(r"SY-SUBRC|IS\s+(NOT\s+)?(ASSIGNED|BOUND)|LINE_EXISTS", re.I)


def _mk(rule, sev, st: Stmt, title, why, suggestion) -> Finding:
    snippet = st.text if len(st.text) <= 160 else st.text[:157] + "..."
    return Finding(rule, sev, st.line, title, why, suggestion, snippet)


def review(code: str) -> list[Finding]:
    stmts = statements(code)
    found: list[Finding] = []
    stack: list[str] = []  # open loop kinds
    for i, st in enumerate(stmts):
        words = st.upper.split()
        first = words[0] if words else ""
        second = words[1] if len(words) > 1 else ""

        if first in LOOP_CLOSE:
            if stack:
                stack.pop()
            continue

        if first == "LOOP" and "LOOP" in stack:
            found.append(_mk("nested-loop", "medium", st, "Nested LOOP",
                "A LOOP inside another LOOP does inner x outer iterations. It is only a problem when both tables are large.",
                "If the inner table is big, read it with a sorted or hashed table key (READ TABLE ... WITH TABLE KEY) or use LOOP ... WHERE on a sorted table."))
        if first in LOOP_OPEN:
            stack.append(first)

        if first == "SELECT":
            if stack:
                found.append(_mk("select-in-loop", "high", st, "Database SELECT inside a loop",
                    "Each iteration is a separate database round trip; the runtime grows with the number of loop passes.",
                    "Read the data once before the loop (SELECT ... FOR ALL ENTRIES or a JOIN into an internal table) and READ TABLE inside the loop."))
            if _SELECT_STAR.match(st.text):
                single = bool(re.match(r"^SELECT\s+SINGLE", st.text, re.I))
                found.append(_mk("select-star", "low" if single else "medium", st, "SELECT * reads every column",
                    "Wide tables transfer many unused fields, which costs time and memory.",
                    "List only the fields you use (or use a view/CDS) and select INTO a matching structure or table."))
            m = _FAE.search(st.text)
            if m:
                tab = m.group(1).rstrip("[]").lower()
                before = " ".join(s.text for s in stmts[max(0, i - 8): i]).lower()
                guarded = re.search(rf"\b{re.escape(tab)}(\[\])?\s+is\s+not\s+initial|lines\(\s*{re.escape(tab)}(\[\])?\s*\)\s*>\s*0|\bis\s+initial\b.*{re.escape(tab)}|{re.escape(tab)}(\[\])?\s+is\s+initial", before)
                if not guarded:
                    found.append(_mk("fae-empty-check", "high", st, f"FOR ALL ENTRIES on {m.group(1)} without a visible empty check",
                        "If the driver table is empty, FOR ALL ENTRIES ignores the condition and reads ALL rows of the database table.",
                        f"Wrap the SELECT in IF {m.group(1)} IS NOT INITIAL. ... ENDIF. (also remove duplicate keys from the driver table first)."))
            if re.match(r"^SELECT\s+SINGLE\b", st.text, re.I):
                nxt = " ".join(s.text for s in stmts[i + 1: i + 3])
                if not _SYSUBRC_NEAR.search(nxt):
                    found.append(_mk("no-subrc-select", "medium", st, "No sy-subrc check after SELECT SINGLE",
                        "If no row is found the target keeps its old/initial value and the program continues silently.",
                        "Check sy-subrc = 0 right after the statement and handle the 'not found' case."))

        if first == "ENDSELECT":
            found.append(_mk("endselect", "low", st, "SELECT ... ENDSELECT loop",
                "ENDSELECT processes one row at a time while the database cursor stays open.",
                "Use SELECT ... INTO TABLE and then LOOP AT the internal table."))

        if first == "READ" and second == "TABLE":
            nxt = " ".join(s.text for s in stmts[i + 1: i + 3])
            if not _SYSUBRC_NEAR.search(nxt):
                found.append(_mk("no-subrc-read", "medium", st, "No sy-subrc check after READ TABLE",
                    "When the row is missing, the work area keeps its previous content (or a field symbol stays unassigned) and wrong data is used.",
                    "Check sy-subrc = 0 (or IS ASSIGNED for ASSIGNING) before using the result."))
            if stack and re.search(r"\bWITH\s+KEY\b", st.upper) and not re.search(r"BINARY\s+SEARCH|WITH\s+TABLE\s+KEY", st.upper):
                found.append(_mk("read-in-loop", "low", st, "READ TABLE ... WITH KEY inside a loop without BINARY SEARCH",
                    "On a standard table this is a linear search per iteration.",
                    "Sort the table once and add BINARY SEARCH, or use a SORTED/HASHED table and WITH TABLE KEY."))

        if first == "COMMIT" and stack:
            found.append(_mk("commit-in-loop", "medium", st, "COMMIT WORK inside a loop",
                "Committing per iteration is slow and breaks the logical unit of work: a later error cannot roll back earlier rows.",
                "Commit once after the loop, or in agreed packages."))

        if first in ("BREAK", "BREAK-POINT"):
            found.append(_mk("breakpoint", "high", st, "Leftover breakpoint",
                "BREAK-POINT / BREAK <user> stops or dumps the program for other users when transported.",
                "Remove it before the transport, or use an external breakpoint set in the debugger."))

        if re.match(r"^MESSAGE\s+['`]", st.text, re.I):
            found.append(_mk("hardcoded-message", "low", st, "Hard-coded message text",
                "Literal texts cannot be translated and are hard to reuse.",
                "Create the message in a message class (SE91) and use MESSAGE e001(zmsg) or a text symbol."))

        if first == "MOVE" and second not in ("-CORRESPONDING",):
            found.append(_mk("obsolete-move", "low", st, "Obsolete MOVE statement",
                "MOVE x TO y is the old form of y = x.", "Use y = x. (and CORRESPONDING #( ... ) instead of MOVE-CORRESPONDING in new code)."))
        if first == "CALL" and second == "METHOD":
            found.append(_mk("obsolete-call-method", "low", st, "Obsolete CALL METHOD syntax",
                "The functional call is shorter and allows chaining.", "Use lo_obj->method( param = value )."))
        if first == "TABLES":
            found.append(_mk("obsolete-tables", "low", st, "TABLES statement",
                "It creates an implicit global work area and is forbidden inside classes.", "Declare a structure with DATA ls_x TYPE x."))
        if first in _OBSOLETE_ARITH and re.search(r"\b(TO|FROM|BY)\b", st.upper):
            found.append(_mk("obsolete-arith", "low", st, f"Obsolete {first} statement",
                "ADD/SUBTRACT/MULTIPLY/DIVIDE are the old forms of arithmetic.", "Use x = x + 1 (or x += 1 on current releases)."))
        if first in ("DATA", "TYPES", "STATICS") and re.search(r"\bOCCURS\b|WITH\s+HEADER\s+LINE", st.upper):
            found.append(_mk("header-line", "medium", st, "Internal table with header line / OCCURS",
                "Header lines hide whether a name means the table or its work area and are forbidden in classes.",
                "Declare a standard table type and a separate work area (TYPE STANDARD TABLE OF ... WITH DEFAULT KEY)."))

    has_select = any(s.upper.startswith("SELECT") for s in stmts)
    is_program = any(s.upper.split()[:1] in (["REPORT"], ["PROGRAM"]) for s in stmts)
    if is_program and has_select and not re.search(r"AUTHORITY-CHECK", code, re.I):
        found.append(Finding("no-authority-check", "info", 1, "No AUTHORITY-CHECK found",
            "The program reads database data but contains no authorization check.",
            "If the data is sensitive (HR, finance, customer data), add AUTHORITY-CHECK OBJECT ... as the FS requires. Ignore if it is not needed here."))

    found.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.line, f.rule))
    return found
