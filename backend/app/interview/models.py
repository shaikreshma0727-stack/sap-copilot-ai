from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Level = Literal["basic", "intermediate", "advanced"]


class KeyPoint(BaseModel):
    text: str
    # keywords; the point counts as covered if ANY entry is found. "a+b" means both a and b are needed.
    any: list[str] = Field(min_length=1)

    @field_validator("any")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [k.strip().lower() for k in v if k.strip()]

    @model_validator(mode="after")
    def _has_keywords(self) -> "KeyPoint":
        if not self.any:
            raise ValueError(f"key point '{self.text}' needs at least one keyword")
        return self


class Question(BaseModel):
    id: str
    topic: str
    level: Level = "basic"
    question: str
    key_points: list[KeyPoint] = Field(min_length=2)
    model_answer: str
    source: str = "general knowledge - review before relying on it"

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or " " in v:
            raise ValueError("id must be a short word without spaces")
        return v
