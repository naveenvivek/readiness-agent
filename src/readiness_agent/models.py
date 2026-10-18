"""Data contracts shared by the rules engine and, later, the LLM nodes."""

from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


SEVERITY_ORDER = {Severity.BLOCKER: 0, Severity.WARNING: 1, Severity.INFO: 2}


class Rule(BaseModel):
    """One entry from rules/rules.yaml."""

    id: str
    title: str
    severity: Severity
    detector: str
    params: dict
    fix: str


class Finding(BaseModel):
    """A rule that fired, with the evidence that proves it."""

    rule_id: str
    title: str
    severity: Severity
    file: str
    line: int | None = None
    evidence: str
    fix: str
