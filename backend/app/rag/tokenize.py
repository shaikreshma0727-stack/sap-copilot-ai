"""Tokenizer shared by BM25 search and the offline test embedder.

ABAP identifiers look like BAPI_REQUISITION_CREATE or zcl_demo=>method~name.
A plain word-split would never match the query "requisition" against that
identifier, so we emit the whole identifier AND its underscore-separated parts.
"""

import re

_TOKEN_RE = re.compile(r"[a-z0-9_/]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        tokens.append(raw)
        if "_" in raw:
            tokens.extend(p for p in raw.split("_") if len(p) > 1)
    return tokens
