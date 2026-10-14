"""    python -m app.interview.cli validate
    python -m app.interview.cli list
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from app.interview.loader import QuestionBankError, load_dir
from app.interview.service import interview_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.interview.cli")
    ap.add_argument("cmd", choices=["validate", "list"])
    args = ap.parse_args(argv)
    try:
        qs = load_dir(interview_dir())
    except QuestionBankError as exc:
        print(f"INVALID: {exc}")
        return 1
    if args.cmd == "validate":
        print(f"OK: {len(qs)} questions in {interview_dir()}")
    else:
        for topic, n in sorted(Counter(q.topic for q in qs).items()):
            print(f"{n:3}  {topic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
