"""The matcher: manuscript in, ranked shortlist out.

    candidates  ->  conflict filter  ->  rank  ->  top k
      (wide)          (hard wall)      (soft)

The engine owns no state about *who has been invited*; that is passed in via
`recent_invites` so the workflow layer stays the single source of truth for load.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..domain.models import Journal, Manuscript, Person, ReviewerProfile, Work
from ..workflow.reliability import reliability_score
from .candidates import Candidate, ReviewerIndex
from .conflicts import Conflict, ConflictChecker, CoauthorGraph
from .fingerprint import Vectorizer
from .ranking import RankingWeights, Scored, score_candidate


@dataclass(frozen=True)
class MatchConfig:
    top_k: int = 10
    candidate_pool: int = 200
    min_fit: float = 0.05
    coauthor_window_years: int = 5
    enforce_conflicts: bool = True      # False only for evaluation/ablation. Never in production.
    weights: RankingWeights = RankingWeights()


@dataclass
class Recommendation:
    reviewer: ReviewerProfile
    score: float
    fit: float
    reasons: list[str]
    parts: dict[str, float] = field(default_factory=dict)


@dataclass
class MatchResult:
    recommendations: list[Recommendation]
    excluded: dict[str, list[Conflict]]     # reviewer id -> why they were removed
    n_candidates: int


class Matcher:
    def __init__(self, people: dict[str, Person], works: dict[str, Work],
                 reviewers: dict[str, ReviewerProfile], journals: dict[str, Journal],
                 today: date, config: MatchConfig = MatchConfig()) -> None:
        self.people = people
        self.works = works
        self.reviewers = reviewers
        self.journals = journals
        self.today = today
        self.config = config
        self.vectorizer = Vectorizer().fit(w.text for w in works.values())
        self.index = ReviewerIndex(self.vectorizer, works, reviewers, current_year=today.year)
        self.conflicts = ConflictChecker(people, CoauthorGraph(works), config.coauthor_window_years)

    def match(self, manuscript: Manuscript,
              recent_invites: dict[str, int] | None = None,
              invites_this_month: dict[str, int] | None = None) -> MatchResult:
        recent_invites = recent_invites or {}
        invites_this_month = invites_this_month or {}
        journal = self.journals[manuscript.journal_id]

        candidates = self.index.generate(manuscript, self.config.candidate_pool, self.config.min_fit)

        survivors: list[Candidate] = []
        excluded: dict[str, list[Conflict]] = {}
        for c in candidates:
            cs = self.conflicts.check(c.reviewer, manuscript, journal, self.today,
                                      invites_this_month.get(c.reviewer.id, 0))
            if cs and self.config.enforce_conflicts:
                excluded[c.reviewer.id] = cs
            else:
                survivors.append(c)

        scored: list[Scored] = [
            score_candidate(c, reliability_score(c.reviewer.stats),
                            recent_invites.get(c.reviewer.id, 0), self.config.weights)
            for c in survivors
        ]
        scored.sort(key=lambda s: s.score, reverse=True)

        recs = [Recommendation(s.reviewer, s.score, s.candidate.fit, s.reasons, s.parts)
                for s in scored[: self.config.top_k]]
        return MatchResult(recs, excluded, len(candidates))
