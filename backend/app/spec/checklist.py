"""Which topics does the FS mention? Keyword based, so it says "mentioned", never "well specified"."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    pattern: re.Pattern
    question: str


def _t(id_: str, label: str, pattern: str, question: str) -> Topic:
    return Topic(id_, label, re.compile(pattern, re.I), question)


TOPICS: list[Topic] = [
    _t("purpose", "Purpose / business need", r"\b(purpose|objective|business (need|requirement|case)|requirement|goal)\b",
       "What business problem does this solve, and who uses it?"),
    _t("object_type", "Type of development", r"\b(report|interface|enhancement|user[- ]exit|badi|form|smartform|adobe|conversion|upload|alv|odata|idoc|workflow|bapi|fiori|cds|program|batch input|bdc)\b",
       "What kind of object is wanted (report, interface, enhancement, form, conversion, ...)?"),
    _t("selection", "Selection screen / inputs", r"\b(selection[- ]screen|selection criteria|input (field|parameter)|parameters?|select[- ]options?|user enters|filter)\b",
       "Which input fields does the user get, which are mandatory, what are the defaults and value checks?"),
    _t("data_source", "Data sources", r"\b(table|tables|view|cds|bapi|function module|master data|transaction|tcode|fetch|read from|retrieve|extract)\b",
       "Which SAP tables, views or APIs hold the data, and are there custom (Z) tables?"),
    _t("logic", "Processing rules", r"\b(rules?|calculate|calculation|validate|validation|derive|condition|logic|determine|business logic|if the|when the)\b",
       "What are the exact rules, calculations and conditions, including the exceptions?"),
    _t("output", "Output / layout", r"\b(output|alv|layout|column|file|email|e-mail|print|spool|display|download|pdf|report shows)\b",
       "What should the output look like (columns, order, totals, file format, who receives it)?"),
    _t("authorization", "Authorization", r"\b(authori[sz]ation|auth(ority)?[- ]?(check|object)|role|permission)\b",
       "Which authorization checks apply (object, fields, activity), and what happens without authorization?"),
    _t("errors", "Error handling and messages", r"\b(error|exception|message|log|reject|invalid|fail|failure|not found|incorrect)\b",
       "What should happen for bad or missing data, and which messages must the user see?"),
    _t("volume", "Volume, performance, scheduling", r"\b(volume|records|rows|lines|performance|background|batch|job|schedule|scheduled|frequency|daily|weekly|monthly|runtime)\b",
       "How many records are expected, is it run online or in background, and how often?"),
    _t("testing", "Test scenarios / acceptance", r"\b(test|testing|acceptance|scenario|expected result|use case|example)\b",
       "Which test scenarios and expected results define 'done'?"),
]


def evaluate(text: str) -> list[dict]:
    return [{"id": t.id, "label": t.label, "mentioned": bool(t.pattern.search(text)), "question": t.question} for t in TOPICS]


def summary(items: list[dict]) -> str:
    n = sum(1 for i in items if i["mentioned"])
    return f"{n} of {len(items)} topics are mentioned in the FS"
