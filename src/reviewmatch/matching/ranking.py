"""Stage 3 of matching: order the survivors and explain the order.

Score is a weighted sum of a few 0..1 signals:
  fit          topical similarity (from stage 1)
  cited        was this reviewer's work cited by the manuscript? (strong expertise signal)
  reliability  derived reputation: accepts invites, delivers on time, editors rate them well
  load         how many invites they've had recently (penalty: spread the work around)

Weights live in RankingWeights so product can tune them without touching code.
Every recommendation carries an `explain()` list, because an editor will not trust a
number they cannot interrogate.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import ReviewerProfile
from .candidates import Candidate


@dataclass(frozen=True)
class RankingWeights:
    fit: float = 0.55
    cited: float = 0.15
    reliability: float = 0.20
    load: float = 0.10          # subtracted
    load_saturation: int = 3    # this many recent invites = full penalty


@dataclass
class Scored:
    candidate: Candidate
    score: float
    parts: dict[str, float]
    reasons: list[str]

    @property
    def reviewer(self) -> ReviewerProfile:
        return self.candidate.reviewer


def score_candidate(cand: Candidate, reliability: float, recent_invites: int,
                    w: RankingWeights) -> Scored:
    cited = 1.0 if cand.cited_works else 0.0
    load = min(1.0, recent_invites / w.load_saturation) if w.load_saturation else 0.0
    parts = {
        "fit": w.fit * cand.fit,
        "cited": w.cited * cited,
        "reliability": w.reliability * reliability,
        "load": -w.load * load,
    }
    score = sum(parts.values())

    reasons = [f"topic fit {cand.fit:.2f}"]
    if cand.cited_works:
        reasons.append(f"cited in manuscript ({len(cand.cited_works)} work(s))")
    reasons.append(f"reliability {reliability:.2f}")
    if recent_invites:
        reasons.append(f"{recent_invites} recent invite(s), load-balanced down")
    return Scored(cand, score, parts, reasons)
