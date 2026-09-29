"""Stage 1 of matching: cast a wide, cheap net.

We cannot afford to run every check on every reviewer in the world, so first we find
a few hundred plausible people, two ways:

1. **Topic similarity** - compare the manuscript fingerprint to each reviewer's
   fingerprint (a recency-weighted blend of their papers). This is the recommender part.
2. **Citation expansion** - authors of works the manuscript cites. If you cite someone,
   they almost certainly understand your problem. This catches experts whose vocabulary
   differs from the manuscript's.

Both routes produce candidates; the union goes to the conflict filter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.models import Manuscript, ReviewerProfile, Work
from .fingerprint import Vector, Vectorizer, add_scaled, cosine, normalise


@dataclass
class Candidate:
    reviewer: ReviewerProfile
    fit: float                      # cosine similarity, 0..1
    cited_works: list[str] = field(default_factory=list)   # this reviewer's works cited by the manuscript


class ReviewerIndex:
    """Precomputed fingerprint per reviewer, plus a lookup from work -> authors."""

    def __init__(self, vectorizer: Vectorizer, works: dict[str, Work],
                 reviewers: dict[str, ReviewerProfile], current_year: int,
                 half_life_years: float = 5.0) -> None:
        self.vectorizer = vectorizer
        self.works = works
        self.reviewers = reviewers
        self.current_year = current_year
        self.half_life = half_life_years
        self.vectors: dict[str, Vector] = {}
        self.works_by_author: dict[str, list[str]] = {}
        self._build()

    def _recency_weight(self, year: int) -> float:
        age = max(0, self.current_year - year)
        return 0.5 ** (age / self.half_life)   # a 5-year-old paper counts half as much

    def _build(self) -> None:
        for w in self.works.values():
            for a in w.author_ids:
                self.works_by_author.setdefault(a, []).append(w.id)
        for rid in self.reviewers:
            acc: Vector = {}
            for wid in self.works_by_author.get(rid, []):
                w = self.works[wid]
                add_scaled(acc, self.vectorizer.vectorize(w.text), self._recency_weight(w.year))
            self.vectors[rid] = normalise(acc)

    def generate(self, manuscript: Manuscript, top_n: int = 200,
                 min_fit: float = 0.05) -> list[Candidate]:
        mvec = self.vectorizer.vectorize(manuscript.text)

        by_id: dict[str, Candidate] = {}
        # Route 1: topic similarity
        scored = [(cosine(mvec, v), rid) for rid, v in self.vectors.items()]
        scored.sort(reverse=True)
        for fit, rid in scored[:top_n]:
            if fit < min_fit:
                break
            by_id[rid] = Candidate(self.reviewers[rid], fit)

        # Route 2: citation expansion
        for wid in manuscript.reference_ids:
            w = self.works.get(wid)
            if not w:
                continue
            for a in w.author_ids:
                if a not in self.reviewers:
                    continue
                cand = by_id.get(a)
                if cand is None:
                    cand = Candidate(self.reviewers[a], cosine(mvec, self.vectors.get(a, {})))
                    by_id[a] = cand
                cand.cited_works.append(wid)

        return list(by_id.values())
