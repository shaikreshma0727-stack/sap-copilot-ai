from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class ErrorEntry(BaseModel):
    id: str
    title: str = Field(min_length=3, max_length=120)
    runtime_errors: list[str] = Field(default_factory=list)  # ST22 runtime error names, e.g. TIME_OUT
    exceptions: list[str] = Field(default_factory=list)  # exception classes, e.g. CX_SY_ZERODIVIDE
    phrases: list[str] = Field(default_factory=list)  # lower-case text fragments of error messages
    causes: list[str] = Field(min_length=1)
    fix_steps: list[str] = Field(min_length=1)
    tcodes: list[str] = Field(default_factory=list)
    status: Literal["verified", "documented", "unverified"] = "unverified"
    source: str = Field(min_length=3)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        v = v.strip().lower()
        if not ID_RE.match(v):
            raise ValueError("id must be lower-case letters, digits and dashes (2-61 chars)")
        return v

    @field_validator("runtime_errors", "exceptions", "tcodes")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        return [x.strip().upper() for x in v if x.strip()]

    @field_validator("phrases")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [x.strip().lower() for x in v if x.strip()]

    @model_validator(mode="after")
    def _has_signal(self):
        if not (self.runtime_errors or self.exceptions or self.phrases):
            raise ValueError("needs at least one of runtime_errors, exceptions or phrases to match on")
        return self
