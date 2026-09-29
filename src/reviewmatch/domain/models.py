"""Core data model.

Everything else in the package is a function over these objects. Keep them dumb:
no behaviour beyond trivial helpers, so they are easy to serialise and reason about.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class Institution:
    id: str
    name: str


@dataclass
class Person:
    """An academic. May be an author, a reviewer, or both.

    `advisor_id` and `grant_ids` exist purely so the conflict checker can catch the
    two conflicts a co-authorship graph misses: supervisor/student and shared funding.
    """
    id: str
    name: str
    orcid: str | None = None
    institution_id: str | None = None
    advisor_id: str | None = None
    grant_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass
class Work:
    """A published paper. The unit of evidence for 'this person knows topic X'."""
    id: str
    title: str
    abstract: str
    author_ids: tuple[str, ...]
    year: int
    reference_ids: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return f"{self.title}. {self.abstract}"


@dataclass
class Manuscript:
    """An unpublished submission that needs reviewers."""
    id: str
    title: str
    abstract: str
    author_ids: tuple[str, ...]
    journal_id: str
    reference_ids: tuple[str, ...] = ()
    submitted_on: date | None = None

    @property
    def text(self) -> str:
        return f"{self.title}. {self.abstract}"


class BlindMode(str, Enum):
    SINGLE = "single"   # reviewer knows author; author does not know reviewer
    DOUBLE = "double"   # neither knows the other
    OPEN = "open"       # both know


@dataclass
class Journal:
    id: str
    name: str
    publisher_id: str                 # the account that pays honoraria
    honorarium_minor: int = 0         # per completed review, in minor units (pence/cents). 0 = unpaid
    blind_mode: BlindMode = BlindMode.SINGLE
    review_days: int = 21             # default deadline length


@dataclass
class ReviewerPreferences:
    max_reviews_per_month: int = 2
    accepts_paid: bool = True
    accepts_unpaid: bool = True
    blackout: tuple[tuple[date, date], ...] = ()     # inclusive ranges when unavailable
    excluded_journal_ids: frozenset[str] = field(default_factory=frozenset)
    charity_id: str | None = None                    # route honoraria here instead of own balance

    def is_blacked_out(self, on: date) -> bool:
        return any(start <= on <= end for start, end in self.blackout)


@dataclass
class ReviewerStats:
    """Raw observed counts. Reputation is *derived* from these in workflow/reliability.py."""
    invited: int = 0
    accepted: int = 0
    completed: int = 0
    on_time: int = 0
    rating_sum: float = 0.0       # sum of editor ratings, 1..5
    rating_count: int = 0


@dataclass
class ReviewerProfile:
    """A Person who has opted in to reviewing. Wraps the person with preferences + stats."""
    person: Person
    preferences: ReviewerPreferences = field(default_factory=ReviewerPreferences)
    stats: ReviewerStats = field(default_factory=ReviewerStats)
    active: bool = True

    @property
    def id(self) -> str:
        return self.person.id
