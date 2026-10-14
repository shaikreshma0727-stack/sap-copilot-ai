"""Syntax-check ABAP code blocks with abaplint (Phase 4).

abaplint is an open-source ABAP linter that runs without an SAP system. We use two of its
rules only:

  parser_error   the code is not valid ABAP grammar (e.g. 'DATA(x) TYPE string.')
  check_syntax   undeclared variables and similar problems inside a complete program/class

abaplint has no copy of your SAP data dictionary, so it reports every class, table or type it
does not know as 'not found'. Those messages would be wrong most of the time (they exist in a real
system), so they are filtered out. This checker therefore finds grammar and declaration mistakes;
it can NOT tell whether a BAPI, table or field really exists - that is the job of the SAP metadata
catalog (Phase 3).

check_blocks() returns None when abaplint is not installed, so the chat keeps working without it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BIN = BACKEND_DIR / "tools" / "abaplint" / "node_modules" / ".bin" / "abaplint"
TIMEOUT_SECONDS = 30

CONFIG = {
    "global": {"files": "/src/**/*.*", "skipGeneratedGatewayClasses": True},
    "dependencies": [],
    "syntax": {"version": "v758", "errorNamespace": "."},
    "rules": {"parser_error": True, "check_syntax": True},
}

_FENCE = re.compile(r"```[ \t]*abap[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_HEADER = re.compile(r"^\s*(REPORT|PROGRAM|CLASS|INTERFACE|FUNCTION-POOL|FUNCTION)\b", re.IGNORECASE | re.MULTILINE)
_GLOBAL_CLASS = re.compile(r"^\s*CLASS\s+(\w+)\s+DEFINITION\s+PUBLIC\b", re.IGNORECASE | re.MULTILINE)
_METHOD_ONLY = re.compile(r"^\s*(METHOD|ENDMETHOD)\b", re.IGNORECASE | re.MULTILINE)
_ELLIPSIS = re.compile(r"^\s*\.\.\.\s*$", re.MULTILINE)
# Messages that only mean "abaplint does not have this SAP object" - not real mistakes.
_NOT_FOUND_VAR = re.compile(r'^"(\w+)" not found, findTop')
MAX_STATEMENT_LINES = 15
_UNKNOWN_OBJECT = re.compile(
    r"^(Class( or type)?|Interface|Database table( or view)?|Function module|Table|Type|Structure|Data element)\b.*not found"
    r"|unknown class",
    re.IGNORECASE,
)


@dataclass
class Issue:
    block: int  # 1-based index of the code block in the answer
    line: int  # 1-based line inside that block
    rule: str
    message: str
    code_line: str = ""
    statement: str = ""  # whole statement for grammar errors


def extract_abap_blocks(markdown: str) -> list[str]:
    return [m.strip("\n") for m in _FENCE.findall(markdown)]


def is_full_unit(code: str) -> bool:
    """A complete program/class/interface (not a loose snippet)."""
    return bool(_HEADER.search(code))


def is_checkable(code: str) -> bool:
    """Skip fragments that cannot be valid on their own (method bodies, '...' placeholders)."""
    if not code.strip():
        return False
    if _ELLIPSIS.search(code):
        return False
    if _METHOD_ONLY.search(code) and not re.search(r"^\s*CLASS\b", code, re.IGNORECASE | re.MULTILINE):
        return False
    return True


def _binary() -> str | None:
    configured = get_settings().abaplint_bin
    if configured:
        return configured if Path(configured).exists() else None
    if DEFAULT_BIN.exists():
        return str(DEFAULT_BIN)
    return shutil.which("abaplint")


def is_available() -> bool:
    return _binary() is not None


def _parse_json(stdout: str):
    start = stdout.find("[")
    if start == -1:
        return None
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError:
        return None


def run_abaplint(files: dict[str, str]) -> list[dict] | None:
    """Run abaplint over {file name: source}; returns its raw findings or None if unavailable."""
    binary = _binary()
    if binary is None:
        return None
    with tempfile.TemporaryDirectory(prefix="abaplint_") as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        for name, source in files.items():
            (root / "src" / name).write_text(source, encoding="utf-8")
        (root / "abaplint.json").write_text(json.dumps(CONFIG), encoding="utf-8")
        try:
            proc = subprocess.run(
                [binary, "-f", "json", "abaplint.json"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return _parse_json(proc.stdout)


def check_blocks(blocks: list[str], runner=run_abaplint) -> list[Issue] | None:
    """Check each checkable block. Returns the issues found, [] if all clean, None if the
    checker is unavailable. `runner` is injectable for tests."""
    files: dict[str, str] = {}
    owner: dict[str, int] = {}
    full: dict[int, bool] = {}
    for idx, code in enumerate(blocks, 1):
        if not is_checkable(code):
            continue
        m = _GLOBAL_CLASS.search(code)
        name = f"{m.group(1).lower()}.clas.abap" if m else f"zblk{idx}.prog.abap"
        if name in files:
            name = f"zblk{idx}.prog.abap"
        files[name] = code if code.endswith("\n") else code + "\n"
        owner[name] = idx
        full[idx] = is_full_unit(code)
    if not files:
        return []
    raw = runner(files)
    if raw is None:
        return None
    issues: list[Issue] = []
    for item in raw:
        name = Path(str(item.get("file", ""))).name.lower()
        idx = owner.get(name)
        if idx is None:
            continue
        rule = item.get("key", "")
        message = str(item.get("description", ""))
        if rule not in ("parser_error", "check_syntax"):
            continue
        if rule == "check_syntax" and (_UNKNOWN_OBJECT.search(message) or not full[idx]):
            continue  # unknown SAP objects, or declarations missing from a loose snippet
        if rule == "check_syntax":
            var = _NOT_FOUND_VAR.match(message)
            if var and re.search(rf"\b(?:DATA|FINAL)\(\s*{re.escape(var.group(1))}\s*\)", blocks[idx - 1], re.IGNORECASE):
                continue  # declared inline (e.g. CALL FUNCTION ... IMPORTING); abaplint does not follow that
        line = int(item.get("start", {}).get("row", 1))
        end_line = int(item.get("end", {}).get("row", line))
        lines = blocks[idx - 1].splitlines()
        code_line = lines[line - 1].strip() if 0 < line <= len(lines) else ""
        statement = ""
        if rule == "parser_error" and 0 < line <= len(lines):
            last = min(max(end_line, line), line + MAX_STATEMENT_LINES - 1, len(lines))
            statement = "\n".join(lines[line - 1 : last])
        issues.append(Issue(block=idx, line=line, rule=rule, message=message, code_line=code_line, statement=statement))
    issues.sort(key=lambda i: (i.block, i.line))
    return issues
