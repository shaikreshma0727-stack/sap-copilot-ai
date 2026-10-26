"""Deterministic extraction of facts from pasted ST22 dump text or an SAP error message.

Nothing here guesses: a field is filled only when the text literally contains it.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

MAX_INPUT_CHARS = 20000


@dataclass
class Parsed:
    kind: str = "text"  # dump | message | text
    runtime_error: str | None = None
    exception: str | None = None
    short_text: str | None = None
    program: str | None = None
    include: str | None = None
    line: int | None = None
    message_class: str | None = None
    message_number: str | None = None
    transaction: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


_RUNTIME = re.compile(r"Runtime\s+Errors?\s*[:=]?\s+([A-Z][A-Z0-9_]{2,})")
_EXC = re.compile(r"\b(CX_[A-Z0-9_]+)\b")
_PROGRAM = re.compile(r'termination occurred in the ABAP program\s+"?([A-Za-z0-9_/<>]+)"?', re.I)
_MAIN = re.compile(r'main program was\s+"?([A-Za-z0-9_/<>]+)"?', re.I)
_INCLUDE = re.compile(r'of the \(Include\) program\s+"?([A-Za-z0-9_/<>]+)"?', re.I)
_LINE = re.compile(r"\bin line\s+(\d{1,6})\b", re.I)
_TCODE = re.compile(r"(?i:Transaction(?:\s+code)?)\W{0,12}?\s*[:=.\s]\s*\"?([A-Z0-9_/]{2,20})\"?(?![A-Za-z])")
_MSG_CLASS = re.compile(r'Message\s+class\W{0,6}\s*"?([A-Z0-9_/]{1,20})"?', re.I)
_MSG_NUM = re.compile(r'Message\s+number\W{0,6}\s*"?(\d{3})\b', re.I)
_MSG_NO = re.compile(r"Message\s+no\.?\s*:?\s*([A-Z][A-Z0-9_/]{0,19}?)(\d{3})\b")
_MSG_PAREN = re.compile(r"\(([A-Z][A-Z0-9_/]{0,19})\s(\d{3})\)")


def _short_text(text: str) -> str | None:
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "short text":
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt.strip()[:300]
            return None
    return None


def parse(text: str) -> Parsed:
    text = (text or "")[:MAX_INPUT_CHARS]
    p = Parsed()

    m = _RUNTIME.search(text)
    if m:
        p.runtime_error = m.group(1)
        p.kind = "dump"
    m = _EXC.search(text)
    if m:
        p.exception = m.group(1)
    p.short_text = _short_text(text)
    if p.short_text and p.kind == "text":
        p.kind = "dump"

    m = _PROGRAM.search(text) or _MAIN.search(text)
    if m:
        p.program = m.group(1)
    m = _INCLUDE.search(text)
    if m:
        p.include = m.group(1)
    m = _LINE.search(text)
    if m:
        p.line = int(m.group(1))
    m = _TCODE.search(text)
    if m:
        p.transaction = m.group(1)

    m = _MSG_NO.search(text)
    if m:
        p.message_class, p.message_number = m.group(1), m.group(2)
    else:
        c, n = _MSG_CLASS.search(text), _MSG_NUM.search(text)
        if c and n:
            p.message_class, p.message_number = c.group(1).upper(), n.group(1)
        else:
            m = _MSG_PAREN.search(text)
            if m:
                p.message_class, p.message_number = m.group(1), m.group(2)
    if p.message_class and p.kind == "text":
        p.kind = "message"
    return p
