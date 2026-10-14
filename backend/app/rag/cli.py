"""Command-line tool for the knowledge base.

Run from the backend/ folder:
    python -m app.rag.cli ingest ../knowledge_base/raw/abap-cheat-sheets --source abap-cheat-sheets
    python -m app.rag.cli search "how to read an internal table" -k 5
    python -m app.rag.cli stats
    python -m app.rag.cli eval ../evals/retrieval_cases.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.rag.ingest import ingest_folder
from app.rag.retriever import Retriever
from app.rag.service import make_store_and_embedder


def _preview(text: str, n: int = 240) -> str:
    body = text.split("\n", 1)[1] if "\n" in text else text
    return " ".join(body.split())[:n]


def cmd_ingest(args) -> int:
    store, embedder = make_store_and_embedder()
    source = args.source or Path(args.path).resolve().name
    print(f"Embedding with {embedder.name} (first run downloads the model, please wait)...")
    t0 = time.time()

    def progress(done, total):
        print(f"\r  embedded {done}/{total} chunks", end="", flush=True)

    report = ingest_folder(args.path, source, store, embedder, replace_source=not args.keep_old, progress=progress)
    print(
        f"\nSource '{source}': {report.files_chunked}/{report.files_seen} files chunked "
        f"({report.files_empty} empty, {report.skipped} too large) -> {report.chunks} chunks "
        f"in {time.time() - t0:.1f}s. Store now holds {store.count()} chunks."
    )
    return 0


def cmd_search(args) -> int:
    store, embedder = make_store_and_embedder()
    retriever = Retriever(store, embedder)
    filters = {"module": args.module, "technology": args.technology, "object_type": args.object_type, "source": args.source}
    hits = retriever.search(args.query, k=args.k, mode=args.mode, filters=filters)
    if not hits:
        print("No results (is the knowledge base empty? run the ingest command first).")
        return 0
    for i, h in enumerate(hits, 1):
        m = h.metadata
        print(f"\n#{i}  score={h.score:.4f}  vec_rank={h.vector_rank}  bm25_rank={h.bm25_rank}")
        print(f"    {m.get('object_type')} | {m.get('object_name')} | {m.get('path')}  [{m.get('module')}/{m.get('technology')}/{m.get('syntax_era')}]")
        print(f"    {_preview(h.text)}")
    return 0


def cmd_stats(_args) -> int:
    store, embedder = make_store_and_embedder()
    print(f"Embedding backend: {embedder.name}")
    print(f"Total chunks: {store.count()}")
    for src, n in sorted(store.source_counts().items()):
        print(f"  {src}: {n}")
    return 0


def cmd_eval(args) -> int:
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    store, embedder = make_store_and_embedder()
    retriever = Retriever(store, embedder)
    k = args.k
    scored = hits_ok = 0
    mrr_sum = 0.0
    print(f"Mode: {args.mode} | top-{k} | backend: {embedder.name}\n")
    for case in cases:
        q = case["query"]
        needles = [s.lower() for s in case["expect_text_any"]]
        results = retriever.search(q, k=k, mode=args.mode, filters=case.get("filters"))
        rank = next((i for i, h in enumerate(results, 1) if any(n in h.text.lower() for n in needles)), None)
        optional = case.get("needs_own_notes", False)
        tag = " (needs your own notes)" if optional else ""
        status = f"PASS @ rank {rank}" if rank else "FAIL"
        print(f"[{status:>14}] {q}{tag}")
        if not optional:
            scored += 1
            if rank:
                hits_ok += 1
                mrr_sum += 1.0 / rank
    if scored:
        print(f"\nHit@{k}: {hits_ok}/{scored} = {hits_ok / scored:.0%}   MRR: {mrr_sum / scored:.3f}")
    return 0 if scored and hits_ok == scored else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.rag.cli", description="SAP knowledge base tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="chunk, embed and store a folder")
    pi.add_argument("path")
    pi.add_argument("--source", help="name for this source (default: folder name)")
    pi.add_argument("--keep-old", action="store_true", help="do not delete this source's old chunks first")
    pi.set_defaults(fn=cmd_ingest)

    ps = sub.add_parser("search", help="search the knowledge base")
    ps.add_argument("query")
    ps.add_argument("-k", type=int, default=5)
    ps.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid")
    ps.add_argument("--module")
    ps.add_argument("--technology")
    ps.add_argument("--object-type", dest="object_type")
    ps.add_argument("--source")
    ps.set_defaults(fn=cmd_search)

    pt = sub.add_parser("stats", help="show what is stored")
    pt.set_defaults(fn=cmd_stats)

    pe = sub.add_parser("eval", help="run retrieval test cases")
    pe.add_argument("cases")
    pe.add_argument("-k", type=int, default=5)
    pe.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid")
    pe.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
