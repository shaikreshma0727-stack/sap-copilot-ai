"""Code-aware chunking for the SAP knowledge base.

Why not fixed-size chunks? A method cut in half is a bad search result and a bad
prompt. Here ABAP is split along its own structure (class definition, each
method, FORM, FUNCTION, ...), CDS / behavior definitions are kept whole, and
Markdown is split by heading. Only chunks that exceed MAX_CHARS are split further,
at blank lines, with a small overlap.

Every chunk carries metadata (module, object type, syntax era, ...) so search can
filter later, e.g. "only RAP chunks" or "only MM examples".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The embedding model (bge-small) reads about 512 tokens; code is ~3 chars/token.
MAX_CHARS = 1800
OVERLAP_LINES = 3
MAX_COMMENT_LOOKBACK = 15  # lines of ABAP Doc / comments attached above a block


@dataclass
class Chunk:
    text: str  # header + raw content: this is what is embedded, searched and shown
    metadata: dict = field(default_factory=dict)
    id: str = ""


# --------------------------------------------------------------------------- #
# Metadata heuristics
# --------------------------------------------------------------------------- #

_MODULE_KEYWORDS = {
    "MM": ["BAPI_REQUISITION_CREATE", "BAPI_PR_CREATE", "BAPI_PO_CREATE", "BAPI_PO_CREATE1", "BAPI_GOODSMVT_CREATE",
           "EBAN", "EKKO", "EKPO", "MARA", "MARC", "MSEG", "MKPF", "LFA1", "ME21N", "MIGO"],
    "SD": ["VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP", "KNA1", "BAPI_SALESORDER_CREATEFROMDAT2"],
    "FI": ["BKPF", "BSEG", "BSIK", "BSAK", "BSID", "BSAD", "SKA1", "FB01", "BAPI_ACC_DOCUMENT_POST"],
    "CO": ["COEP", "COBK", "CSKS", "CSKT", "AUFK", "BAPI_COSTCENTER_CREATEMULTIPLE"],
    "PP": ["AFKO", "AFPO", "MAST", "STPO", "CRHD", "RESB"],
    "HCM": ["PA0001", "PA0002", "PA2001", "PERNR", "HR_READ_INFOTYPE"],
}
_MODULE_RES = {
    mod: [(kw, re.compile(rf"\b{re.escape(kw)}\b", re.I)) for kw in kws] for mod, kws in _MODULE_KEYWORDS.items()
}


def detect_module(text: str) -> str:
    """Best-guess SAP module. Names with '_' (BAPIs) are strong signals; bare table
    names need at least two distinct matches, to avoid false hits in prose."""
    best, best_score = "general", 0
    for mod, pats in _MODULE_RES.items():
        score = 0
        for kw, pat in pats:
            if pat.search(text):
                score += 2 if "_" in kw else 1
        if score > best_score:
            best, best_score = mod, score
    return best if best_score >= 2 else "general"


_RAP_RE = re.compile(
    r"\b(MODIFY|READ|COMMIT)\s+ENTIT(Y|IES)\b|\bFOR\s+BEHAVIO(U)?R\b|\bBEHAVIO(U)?R\s+DEFINITION\b"
    r"|\bcl_abap_behv\w*|\bderived\s+type\s+table\s+for\s+(action|create|update|read)\b",
    re.I,
)


def detect_technology(text: str, language: str) -> str:
    if language == "bdef":
        return "rap"
    if language == "cds":
        return "cds"
    if _RAP_RE.search(text):
        return "rap"
    return "abap"


_MODERN_RE = re.compile(
    r"@?DATA\(|FINAL\(|\bVALUE\s+#?\(|\bNEW\s+#?\(|\bCONV\s+#?\(|\bCOND\s+#?\(|\bSWITCH\s+#?\(|\bREF\s+#\(|\bCORRESPONDING\s+#?\(|\bFOR\s+\w+\s+IN\b",
    re.I,
)
_CLASSIC_RE = re.compile(
    r"^\s*(FORM|TABLES|MOVE|MOVE-CORRESPONDING|REFRESH|WRITE)\b|\bOCCURS\b|\bHEADER\s+LINE\b|\bDESCRIBE\s+TABLE\b",
    re.I | re.M,
)


def detect_syntax_era(text: str, language: str) -> str:
    """'modern' (7.4+/S4/cloud-style syntax), 'classic' (older style) or 'mixed'.
    This is about the SYNTAX STYLE of the code, not a guarantee of the system release."""
    if language in ("cds", "bdef"):
        return "modern"
    modern, classic = bool(_MODERN_RE.search(text)), bool(_CLASSIC_RE.search(text))
    if modern and not classic:
        return "modern"
    if classic and not modern:
        return "classic"
    return "mixed"


def _base_metadata(*, source: str, path: str, language: str, text_for_detection: str) -> dict:
    return {
        "source": source,
        "path": path,
        "language": language,
        "module": detect_module(text_for_detection),
        "technology": detect_technology(text_for_detection, language),
        "syntax_era": detect_syntax_era(text_for_detection, language),
    }


# --------------------------------------------------------------------------- #
# Splitting oversized text
# --------------------------------------------------------------------------- #


def _hard_wrap(line: str, limit: int) -> list[str]:
    return [line[i : i + limit] for i in range(0, len(line), limit)] or [""]


def split_lines(lines: list[str], max_chars: int = MAX_CHARS, overlap: int = OVERLAP_LINES) -> list[list[str]]:
    """Split lines into windows of <= max_chars, preferring to cut at a blank line,
    and repeating the last `overlap` lines at the start of the next window."""
    flat: list[str] = []
    for ln in lines:
        flat.extend(_hard_wrap(ln, max_chars) if len(ln) > max_chars else [ln])

    if sum(len(x) + 1 for x in flat) <= max_chars:
        return [flat]

    windows: list[list[str]] = []
    start = 0
    n = len(flat)
    while start < n:
        size, end = 0, start
        while end < n and (size + len(flat[end]) + 1 <= max_chars or end == start):
            size += len(flat[end]) + 1
            end += 1
        if end < n:  # not the last window: try to back up to a blank line in the 2nd half
            half = start + (end - start) // 2
            cut = next((j for j in range(end - 1, half, -1) if not flat[j].strip()), None)
            if cut is not None:
                end = cut + 1
        windows.append(flat[start:end])
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return windows


# --------------------------------------------------------------------------- #
# ABAP
# --------------------------------------------------------------------------- #

_CLASS_DEF = re.compile(r"^\s*CLASS\s+([\w/]+)\s+DEFINITION\b", re.I)
_CLASS_IMPL = re.compile(r"^\s*CLASS\s+([\w/]+)\s+IMPLEMENTATION\b", re.I)
_DEFER_OR_LOAD = re.compile(r"\b(DEFERRED|LOAD)\b", re.I)
_ENDCLASS = re.compile(r"^\s*ENDCLASS\b", re.I)
_INTF = re.compile(r"^\s*INTERFACE\s+([\w/]+)\b", re.I)
_ENDINTF = re.compile(r"^\s*ENDINTERFACE\b", re.I)
_METHOD = re.compile(r"^\s*METHOD\s+([\w~/]+)\s*(\.|BY\b)", re.I)
_ENDMETHOD = re.compile(r"^\s*ENDMETHOD\b", re.I)
_FORM = re.compile(r"^\s*FORM\s+([\w/-]+)\b", re.I)
_ENDFORM = re.compile(r"^\s*ENDFORM\b", re.I)
_FUNCTION = re.compile(r"^\s*FUNCTION\s+([\w/]+)\s*\.", re.I)
_ENDFUNCTION = re.compile(r"^\s*ENDFUNCTION\b", re.I)
_MODULE = re.compile(r"^\s*MODULE\s+([\w/]+)\s+(OUTPUT|INPUT)\b", re.I)
_ENDMODULE = re.compile(r"^\s*ENDMODULE\b", re.I)
_REPORT = re.compile(r"^\s*(REPORT|PROGRAM)\s+([\w/]+)", re.I)


def _is_code(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith('"') and not line.startswith("*")


def _is_comment(line: str) -> bool:
    s = line.strip()
    return s.startswith('"') or line.startswith("*")


def _file_kind(path: str) -> str:
    p = path.lower()
    if ".clas.testclasses." in p:
        return "clas_tests"
    if ".clas.locals_" in p or ".clas.macros." in p:
        return "clas_locals"
    if ".clas." in p:
        return "clas"
    if ".prog." in p:
        return "prog"
    if ".intf." in p:
        return "intf"
    if ".fugr." in p:
        return "fugr"
    return "abap"


@dataclass
class _Span:
    kind: str
    name: str
    start: int  # inclusive line index
    end: int  # inclusive line index
    parent: str = ""


def _find_abap_spans(lines: list[str]) -> list[_Span]:
    spans: list[_Span] = []
    active: _Span | None = None
    impl_class = ""
    method_start: tuple[str, int] | None = None
    last_end = -1

    def begin(kind: str, name: str, idx: int) -> _Span:
        start = idx
        # attach contiguous comment lines directly above (ABAP Doc, explanations)
        lookback = 0
        while start - 1 > last_end and _is_comment(lines[start - 1]) and lookback < MAX_COMMENT_LOOKBACK:
            start -= 1
            lookback += 1
        return _Span(kind, name, start, idx)

    for idx, line in enumerate(lines):
        if not _is_code(line):
            continue
        if active is None:
            if (m := _CLASS_DEF.match(line)) and not _DEFER_OR_LOAD.search(line):
                active = begin("class_definition", m.group(1), idx)
            elif m := _CLASS_IMPL.match(line):
                impl_class = m.group(1)
                active = _Span("class_implementation", impl_class, idx, idx)
            elif (m := _INTF.match(line)) and not _DEFER_OR_LOAD.search(line):
                active = begin("interface", m.group(1), idx)
            elif m := _FORM.match(line):
                active = begin("form", m.group(1), idx)
            elif m := _FUNCTION.match(line):
                active = begin("function", m.group(1), idx)
            elif m := _MODULE.match(line):
                active = begin("module", m.group(1), idx)
            continue

        if active.kind == "class_definition" and _ENDCLASS.match(line):
            active.end = idx
            spans.append(active)
            last_end, active = idx, None
        elif active.kind == "interface" and _ENDINTF.match(line):
            active.end = idx
            spans.append(active)
            last_end, active = idx, None
        elif active.kind == "form" and _ENDFORM.match(line):
            active.end = idx
            spans.append(active)
            last_end, active = idx, None
        elif active.kind == "function" and _ENDFUNCTION.match(line):
            active.end = idx
            spans.append(active)
            last_end, active = idx, None
        elif active.kind == "module" and _ENDMODULE.match(line):
            active.end = idx
            spans.append(active)
            last_end, active = idx, None
        elif active.kind == "class_implementation":
            if method_start is None and (m := _METHOD.match(line)):
                # attach comments above the METHOD statement
                s = idx
                lookback = 0
                while s - 1 > max(last_end, active.start) and _is_comment(lines[s - 1]) and lookback < MAX_COMMENT_LOOKBACK:
                    s -= 1
                    lookback += 1
                method_start = (m.group(1), s)
            elif method_start is not None and _ENDMETHOD.match(line):
                spans.append(_Span("method", method_start[0], method_start[1], idx, parent=impl_class))
                last_end = idx
                method_start = None
            elif method_start is None and _ENDCLASS.match(line):
                active.end = idx
                last_end, active = idx, None
    return spans


def chunk_abap(text: str, path: str, source: str) -> list[Chunk]:
    lines = text.splitlines()
    spans = _find_abap_spans(lines)
    file_kind = _file_kind(path)
    is_test = file_kind == "clas_tests"
    chunks: list[Chunk] = []
    covered = [False] * len(lines)

    def emit(kind: str, name: str, parent: str, start: int, end: int):
        body_lines = lines[start : end + 1]
        windows = split_lines(body_lines)
        label = f"{parent}=>{name}" if parent else name
        for i, win in enumerate(windows, 1):
            part = f" (part {i}/{len(windows)})" if len(windows) > 1 else ""
            header = f"ABAP {kind.replace('_', ' ')}: {label}{part} | file: {path}"
            content = "\n".join(win)
            meta = _base_metadata(source=source, path=path, language="abap", text_for_detection=content)
            meta.update(
                object_type=kind,
                object_name=label,
                class_name=parent if kind == "method" else (name if "class" in kind else ""),
                method_name=name if kind == "method" else "",
                file_kind=file_kind,
                is_test=is_test,
                part=i,
                parts=len(windows),
                start_line=start + 1,
                end_line=end + 1,
            )
            chunks.append(Chunk(text=f"{header}\n{content}", metadata=meta))

    for sp in spans:
        for i in range(sp.start, sp.end + 1):
            covered[i] = True
        emit(sp.kind, sp.name, sp.parent, sp.start, sp.end)

    # Everything outside classes/forms/functions: classic report body, includes, etc.
    stem = path.rsplit("/", 1)[-1].split(".")[0]
    report_name = stem
    for ln in lines:
        if (m := _REPORT.match(ln)) and _is_code(ln):
            report_name = m.group(2)
            break
    i = 0
    while i < len(lines):
        if covered[i] or not lines[i].strip():
            i += 1
            continue
        j = i
        while j + 1 < len(lines) and not covered[j + 1]:
            j += 1
        run = lines[i : j + 1]
        if sum(1 for x in run if _is_code(x)) >= 2:  # skip stray comment-only leftovers
            emit("report_block", report_name, "", i, j)
        i = j + 1
    return chunks


# --------------------------------------------------------------------------- #
# CDS / behavior definitions (kept whole; they are short and self-contained)
# --------------------------------------------------------------------------- #

_CDS_DEFINE = re.compile(
    r"\bdefine\s+(root\s+)?(view\s+entity|view|abstract\s+entity|custom\s+entity|table\s+function|hierarchy"
    r"|service|transient\s+view\s+entity)\s+([\w/]+)",
    re.I,
)
_BDEF_DEFINE = re.compile(r"\bdefine\s+behavio(?:u)?r\s+for\s+([\w/]+)", re.I)


def _whole_file_chunks(text: str, path: str, source: str, language: str, kind: str, name: str, label: str) -> list[Chunk]:
    windows = split_lines(text.splitlines())
    out = []
    for i, win in enumerate(windows, 1):
        part = f" (part {i}/{len(windows)})" if len(windows) > 1 else ""
        content = "\n".join(win)
        meta = _base_metadata(source=source, path=path, language=language, text_for_detection=content)
        meta.update(object_type=kind, object_name=name, part=i, parts=len(windows), is_test=False)
        out.append(Chunk(text=f"{label}: {name}{part} | file: {path}\n{content}", metadata=meta))
    return out


def chunk_cds(text: str, path: str, source: str) -> list[Chunk]:
    m = _CDS_DEFINE.search(text)
    if m:
        kind = "cds_" + re.sub(r"\s+", "_", m.group(2).lower())
        name = m.group(3)
    else:
        kind, name = "cds_source", path.rsplit("/", 1)[-1].split(".")[0]
    return _whole_file_chunks(text, path, source, "cds", kind, name, "CDS " + kind.removeprefix("cds_").replace("_", " "))


def chunk_bdef(text: str, path: str, source: str) -> list[Chunk]:
    m = _BDEF_DEFINE.search(text)
    name = m.group(1) if m else path.rsplit("/", 1)[-1].split(".")[0]
    return _whole_file_chunks(text, path, source, "bdef", "behavior_definition", name, "RAP behavior definition")


# --------------------------------------------------------------------------- #
# Markdown / notes
# --------------------------------------------------------------------------- #

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_MIN_DOC_CHARS = 40


def _markdown_sections(text: str) -> list[tuple[list[str], list[str]]]:
    sections: list[tuple[list[str], list[str]]] = []
    stack: list[tuple[int, str]] = []
    current: list[str] = []
    crumbs: list[str] = []
    in_fence = False

    def flush():
        if any(x.strip() for x in current):
            sections.append((list(crumbs), list(current)))

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            flush()
            current = []
            level, title = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            crumbs = [t for _, t in stack]
        else:
            current.append(line)
    flush()
    return sections


def _pack_blocks(lines: list[str]) -> list[list[str]]:
    """Group a section's lines into text paragraphs and fenced code blocks, then pack
    them greedily into <= MAX_CHARS windows without cutting a code fence in half."""
    blocks: list[list[str]] = []
    cur: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            if not in_fence and cur:
                blocks.append(cur)
                cur = []
            cur.append(line)
            if in_fence:
                blocks.append(cur)
                cur = []
            in_fence = not in_fence
        elif not in_fence and not line.strip():
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    windows: list[list[str]] = []
    buf: list[str] = []
    size = 0
    for blk in blocks:
        blk_size = sum(len(x) + 1 for x in blk)
        if blk_size > MAX_CHARS:
            if buf:
                windows.append(buf)
                buf, size = [], 0
            windows.extend(split_lines(blk))
            continue
        if buf and size + blk_size + 1 > MAX_CHARS:
            windows.append(buf)
            buf, size = [], 0
        if buf:
            buf.append("")
            size += 1
        buf.extend(blk)
        size += blk_size
    if buf:
        windows.append(buf)
    return windows


_BACK_TO_TOP = re.compile(r"back to top", re.I)
_ANCHOR_LINK_LINE = re.compile(r"^\s*[-*+]?\s*\[[^\]]*\]\(#[^)]*\)\s*$")


def _strip_boilerplate(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not (_BACK_TO_TOP.search(ln) and len(ln) < 200)]


def _is_toc(lines: list[str]) -> bool:
    real = [ln for ln in lines if ln.strip()]
    if not real:
        return False
    hits = sum(1 for ln in real if _ANCHOR_LINK_LINE.match(ln))
    return hits / len(real) >= 0.8


def chunk_markdown(text: str, path: str, source: str) -> list[Chunk]:
    doc_title = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("_", " ")
    chunks: list[Chunk] = []
    for crumbs, body in _markdown_sections(text):
        body = _strip_boilerplate(body)
        if _is_toc(body):
            continue
        windows = _pack_blocks(body)
        trail = " > ".join(crumbs) if crumbs else doc_title
        for i, win in enumerate(windows, 1):
            content = "\n".join(win).strip()
            if len(re.sub(r"\s+", "", content)) < _MIN_DOC_CHARS:
                continue
            part = f" (part {i}/{len(windows)})" if len(windows) > 1 else ""
            meta = _base_metadata(source=source, path=path, language="markdown", text_for_detection=content)
            meta.update(
                object_type="doc_section",
                object_name=trail,
                has_code="```" in content or "~~~" in content,
                part=i,
                parts=len(windows),
                is_test=False,
            )
            chunks.append(Chunk(text=f"Doc: {doc_title} > {trail}{part} | file: {path}\n{content}", metadata=meta))
    return chunks


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #


def chunk_file(text: str, path: str, source: str) -> list[Chunk]:
    p = path.lower()
    if p.endswith(".abap"):
        return chunk_abap(text, path, source)
    if p.endswith(".asddls"):
        return chunk_cds(text, path, source)
    if p.endswith(".asbdef"):
        return chunk_bdef(text, path, source)
    if p.endswith((".md", ".markdown", ".txt")):
        return chunk_markdown(text, path, source)
    return []
