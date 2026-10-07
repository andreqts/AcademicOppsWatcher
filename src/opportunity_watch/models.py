from dataclasses import dataclass
from typing import Literal


@dataclass
class RawResult:
    title: str | None
    url: str | None
    body: str
    source_site: str
    query: str


@dataclass
class Candidate:
    id: str
    title: str
    url: str
    source_site: str
    first_seen: str
    last_seen: str
    miss_count: int
    verdict: Literal["genuine", "false_positive"]
    notified: bool


@dataclass
class ValidationResult:
    candidate_id: str
    verdict: Literal["genuine", "false_positive", "failed"]
    confidence: float | None
    method: Literal["jev", "free_fallback"]
    error: str | None


# why: SPEC_DEVIATION - timestamp precedes excluded (design.md lists it after), because a
# dataclass field without a default cannot follow one with a default.
@dataclass
class FailureRecord:
    type: Literal["search", "validation", "email", "config"]
    # invariant: never an email address (AD-001).
    target: str
    message: str
    timestamp: str
    excluded: bool = False


@dataclass
class RunSummary:
    queries_run: int
    candidates_found: int
    validated_count: int
    new_count: int
    excluded_count: int
    failures: list[FailureRecord]


@dataclass
class NotifyResult:
    # invariant: a count, never addresses (AD-001).
    sent_to: int
    skipped: bool
    failure: FailureRecord | None
