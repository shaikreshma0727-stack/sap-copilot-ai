from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.interview.models import Question


class QuestionBankError(Exception):
    """A question YAML file is malformed. The message names the file and the question."""


def load_dir(path: str | Path) -> list[Question]:
    folder = Path(path)
    if not folder.is_dir():
        return []
    out: list[Question] = []
    seen: dict[str, str] = {}
    for file in sorted(list(folder.glob("*.yaml")) + list(folder.glob("*.yml"))):
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
        except yaml.YAMLError as exc:
            raise QuestionBankError(f"{file.name}: not valid YAML: {exc}") from exc
        if not isinstance(data, list):
            raise QuestionBankError(f"{file.name}: the file must be a list of questions")
        for i, raw in enumerate(data, 1):
            try:
                q = Question.model_validate(raw)
            except ValidationError as exc:
                label = raw.get("id", f"#{i}") if isinstance(raw, dict) else f"#{i}"
                first = exc.errors()[0]
                where = ".".join(str(p) for p in first["loc"])
                raise QuestionBankError(f"{file.name}, question {label}: {where}: {first['msg']}") from exc
            if q.id in seen:
                raise QuestionBankError(f"{file.name}: question id '{q.id}' is already used in {seen[q.id]}")
            seen[q.id] = file.name
            out.append(q)
    return out
