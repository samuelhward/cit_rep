"""Stage 2 of matching: hard filters.

A conflict of interest is not a score penalty; it is a wall. A reviewer with a conflict
is removed no matter how good the topical fit. Each rule returns a human-readable reason
so editors can see (and audit) why someone was excluded.

Rules, in the order they run (cheapest first):
  - is an author of the manuscript
  - reviewer opted out of this journal / inactive
  - unavailable (blackout dates, monthly cap already hit)
  - co-authored with any author within `coauthor_window_years`
  - same institution as any author
  - supervisor/student relationship with any author
  - shares a grant with any author
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.models import Journal, Manuscript, Person, ReviewerProfile, Work


@dataclass(frozen=True)
class Conflict:
    rule: str
    detail: str


class CoauthorGraph:
    """Who has written with whom, and when. Built once from the works corpus."""

    def __init__(self, works: dict[str, Work]) -> None:
        self.last_coauthored: dict[tuple[str, str], int] = {}
        for w in works.values():
            authors = w.author_ids
            for i, a in enumerate(authors):
                for b in authors[i + 1:]:
                    key = (a, b) if a < b else (b, a)
                    if w.year > self.last_coauthored.get(key, -1):
                        self.last_coauthored[key] = w.year

    def last_year_together(self, a: str, b: str) -> int | None:
        key = (a, b) if a < b else (b, a)
        return self.last_coauthored.get(key)


class ConflictChecker:
    def __init__(self, people: dict[str, Person], graph: CoauthorGraph,
                 coauthor_window_years: int = 5) -> None:
        self.people = people
        self.graph = graph
        self.window = coauthor_window_years

    def check(self, reviewer: ReviewerProfile, manuscript: Manuscript, journal: Journal,
              today: date, invites_this_month: int = 0) -> list[Conflict]:
        conflicts: list[Conflict] = []
        r = reviewer.person
        authors = [self.people[a] for a in manuscript.author_ids if a in self.people]

        if r.id in manuscript.author_ids:
            return [Conflict("author", "is an author of the manuscript")]
        if not reviewer.active:
            return [Conflict("inactive", "reviewer account inactive")]
        if journal.id in reviewer.preferences.excluded_journal_ids:
            return [Conflict("opted_out", f"opted out of {journal.name}")]
        if journal.honorarium_minor > 0 and not reviewer.preferences.accepts_paid:
            return [Conflict("payment_pref", "does not accept paid reviews")]
        if journal.honorarium_minor == 0 and not reviewer.preferences.accepts_unpaid:
            return [Conflict("payment_pref", "does not accept unpaid reviews")]
        if reviewer.preferences.is_blacked_out(today):
            conflicts.append(Conflict("unavailable", "blackout period"))
        if invites_this_month >= reviewer.preferences.max_reviews_per_month:
            conflicts.append(Conflict("capacity", "monthly review cap reached"))

        for a in authors:
            yr = self.graph.last_year_together(r.id, a.id)
            if yr is not None and today.year - yr <= self.window:
                conflicts.append(Conflict("coauthor", f"co-authored with {a.name} in {yr}"))
            if r.institution_id and r.institution_id == a.institution_id:
                conflicts.append(Conflict("institution", f"same institution as {a.name}"))
            if r.advisor_id == a.id or a.advisor_id == r.id:
                conflicts.append(Conflict("advisor", f"supervisor/student relationship with {a.name}"))
            shared = r.grant_ids & a.grant_ids
            if shared:
                conflicts.append(Conflict("grant", f"shares grant {sorted(shared)[0]} with {a.name}"))
        return conflicts
