"""Catalog commands (run inside backend/ with the venv on):

    python -m app.catalog.cli validate
    python -m app.catalog.cli stats
    python -m app.catalog.cli show BAPI_PR_CREATE
    python -m app.catalog.cli check some_code.abap
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.catalog.checker import check_code
from app.catalog.index import Catalog, facts_for
from app.catalog.loader import CatalogError, load_dir
from app.catalog.service import catalog_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.catalog.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("stats")
    show = sub.add_parser("show")
    show.add_argument("name")
    chk = sub.add_parser("check")
    chk.add_argument("file")
    args = ap.parse_args(argv)

    try:
        entries = load_dir(catalog_dir())
    except CatalogError as exc:
        print(f"INVALID: {exc}")
        return 1
    catalog = Catalog(entries)

    if args.cmd == "validate":
        print(f"OK: {len(entries)} entries in {catalog_dir()}")
    elif args.cmd == "stats":
        print(json.dumps(catalog.stats(), indent=2))
    elif args.cmd == "show":
        e = catalog.get(args.name)
        if not e:
            print(f"{args.name.upper()} is not in the catalog")
            return 1
        print(facts_for([e]))
    elif args.cmd == "check":
        code = Path(args.file).read_text(encoding="utf-8")
        findings = check_code(code, catalog)
        if not findings:
            print("Nothing in this code is known to the catalog.")
        for f in findings:
            print(f"[{f.level:9}] {f.message}" + (f"  (status: {f.status})" if f.status else ""))
        return 1 if any(f.level == "conflict" for f in findings) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
