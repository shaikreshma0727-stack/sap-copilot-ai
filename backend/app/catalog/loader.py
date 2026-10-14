from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.catalog.models import Entry


class CatalogError(Exception):
    """A catalog YAML file is malformed. The message names the file and the entry."""


def load_dir(path: str | Path) -> list[Entry]:
    folder = Path(path)
    if not folder.is_dir():
        return []
    entries: list[Entry] = []
    seen: dict[str, str] = {}
    for file in sorted(list(folder.glob("*.yaml")) + list(folder.glob("*.yml"))):
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
        except yaml.YAMLError as exc:
            raise CatalogError(f"{file.name}: not valid YAML: {exc}") from exc
        if not isinstance(data, list):
            raise CatalogError(f"{file.name}: the file must be a list of entries")
        for i, raw in enumerate(data, 1):
            try:
                entry = Entry.model_validate(raw)
            except ValidationError as exc:
                label = raw.get("name", f"#{i}") if isinstance(raw, dict) else f"#{i}"
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first["loc"])
                raise CatalogError(f"{file.name}, entry {label}: {where}: {first['msg']}") from exc
            if entry.name in seen:
                raise CatalogError(f"{file.name}: {entry.name} is already defined in {seen[entry.name]}")
            seen[entry.name] = file.name
            entries.append(entry)
    return entries
