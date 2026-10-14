from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Status = Literal["verified", "documented", "unverified"]
Kind = Literal["function_module", "structure", "table", "table_type"]
Direction = Literal["import", "export", "tables", "changing"]


class Param(BaseModel):
    """A function module parameter, direction seen from the function module's side
    (CALL FUNCTION ... EXPORTING fills an 'import' parameter, IMPORTING reads an 'export' one)."""

    name: str
    direction: Direction
    type: str = ""
    description: str = ""

    @field_validator("name", "type")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class FieldDef(BaseModel):
    name: str
    type: str = ""
    key: bool = False

    @field_validator("name", "type")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class Entry(BaseModel):
    name: str
    kind: Kind
    module: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)  # lower-case phrases that should surface the entry
    status: Status = "unverified"
    source: str = ""
    complete: bool = False  # True = the params/fields list is exhaustive (unknown names are errors)
    params: list[Param] = Field(default_factory=list)
    fields: list[FieldDef] = Field(default_factory=list)
    line_type: str = ""  # for kind=table_type: the structure one row has
    notes: str = ""

    @field_validator("name", "line_type")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("keywords")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [k.strip().lower() for k in v if k.strip()]

    @field_validator("fields", mode="before")
    @classmethod
    def _fields_from_strings(cls, v):
        return [{"name": f} if isinstance(f, str) else f for f in (v or [])]

    @model_validator(mode="after")
    def _consistent(self) -> "Entry":
        if self.status in ("verified", "documented") and not self.source.strip():
            raise ValueError(f"{self.name}: status '{self.status}' needs a 'source'")
        if self.kind == "function_module" and self.fields:
            raise ValueError(f"{self.name}: a function module has 'params', not 'fields'")
        if self.kind in ("structure", "table") and self.params:
            raise ValueError(f"{self.name}: a {self.kind} has 'fields', not 'params'")
        if self.kind == "table_type" and not self.line_type:
            raise ValueError(f"{self.name}: a table_type needs 'line_type'")
        return self

    def param(self, name: str) -> Param | None:
        name = name.upper()
        return next((p for p in self.params if p.name == name), None)

    def has_field(self, name: str) -> bool:
        name = name.upper()
        return any(f.name == name for f in self.fields)
