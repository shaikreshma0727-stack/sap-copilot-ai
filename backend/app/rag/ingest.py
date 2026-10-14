"""Walk a folder, chunk every supported file, embed, and store."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from app.rag.chunker import Chunk, chunk_file
from app.rag.embedder import Embedder
from app.rag.store import KnowledgeStore

SUPPORTED_EXT = (".abap", ".asddls", ".asbdef", ".md", ".markdown", ".txt")
SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__", ".venv", "images", "img", "assets"}
SKIP_NAME_PREFIXES = ("license", "code_of_conduct", "contributing", "security", "changelog")
MAX_FILE_BYTES = 1_000_000
BATCH = 64


@dataclass
class IngestReport:
    files_seen: int = 0
    files_chunked: int = 0
    files_empty: int = 0
    chunks: int = 0
    skipped: int = 0


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.lower().endswith(SUPPORTED_EXT) and not name.lower().startswith(SKIP_NAME_PREFIXES):
                yield Path(dirpath) / name


def chunk_id(source: str, chunk: Chunk) -> str:
    """Stable id: re-ingesting unchanged content overwrites instead of duplicating."""
    m = chunk.metadata
    key = f"{source}|{m.get('path')}|{m.get('object_name')}|{m.get('part')}|{chunk.text}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def collect_chunks(root: Path, source: str, report: IngestReport | None = None) -> list[Chunk]:
    report = report or IngestReport()
    out: list[Chunk] = []
    for path in iter_files(root):
        report.files_seen += 1
        if path.stat().st_size > MAX_FILE_BYTES:
            report.skipped += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        chunks = chunk_file(text, rel, source)
        if not chunks:
            report.files_empty += 1
            continue
        report.files_chunked += 1
        for c in chunks:
            c.id = chunk_id(source, c)
        out.extend(chunks)
    report.chunks = len(out)
    return out


def ingest_folder(
    root: str | Path,
    source: str,
    store: KnowledgeStore,
    embedder: Embedder,
    replace_source: bool = True,
    progress=None,
) -> IngestReport:
    """replace_source=True first deletes this source's old chunks, so removed or renamed
    files do not linger in search results."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder not found: {root}")
    report = IngestReport()
    chunks = collect_chunks(root, source, report)
    if replace_source:
        store.delete_source(source)

    # de-duplicate ids inside this run (identical chunks in different files are rare but possible)
    seen: set[str] = set()
    unique = [c for c in chunks if not (c.id in seen or seen.add(c.id))]

    for i in range(0, len(unique), BATCH):
        batch = unique[i : i + BATCH]
        vectors = embedder.embed_documents([c.text for c in batch])
        store.upsert(
            ids=[c.id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[c.metadata for c in batch],
            embeddings=vectors,
        )
        if progress:
            progress(min(i + BATCH, len(unique)), len(unique))
    report.chunks = len(unique)
    return report
