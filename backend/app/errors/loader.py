from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.errors.models import ErrorEntry


class ErrorBankError(Exception):
    """An error-knowledge YAML file is malformed. The message names the file and the entry."""


def load_dir(path: str | Path) -> list[ErrorEntry]:
    folder = Path(path)
    if not folder.is_dir():
        return []
    out: list[ErrorEntry] = []
    seen: dict[str, str] = {}
    for file in sorted(list(folder.glob("*.yaml")) + list(folder.glob("*.yml"))):
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
        except yaml.YAMLError as exc:
            raise ErrorBankError(f"{file.name}: not valid YAML: {exc}") from exc
        if not isinstance(data, list):
            raise ErrorBankError(f"{file.name}: the file must be a list of entries")
        for i, raw in enumerate(data, 1):
            try:
                e = ErrorEntry.model_validate(raw)
            except ValidationError as exc:
                label = raw.get("id", f"#{i}") if isinstance(raw, dict) else f"#{i}"
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first["loc"])
                raise ErrorBankError(f"{file.name}, entry {label}: {where}: {first['msg']}") from exc
            if e.id in seen:
                raise ErrorBankError(f"{file.name}: entry id '{e.id}' is already used in {seen[e.id]}")
            seen[e.id] = file.name
            out.append(e)
    return out
