"""Reviewer reputation, derived from behaviour rather than declared.

Three rates, each Bayesian-smoothed so a brand-new reviewer starts at a sensible prior
instead of 0/0, and a single review cannot swing the score to 0 or 1:

  accept rate   accepted / invited       (do they say yes?)
  on-time rate  on_time / completed      (do they deliver when they say?)
  rating        mean editor rating / 5   (was the review any good?)

Prior pseudo-counts (`PRIOR_N`) act like "we've already seen this many average
outcomes". Bigger prior = slower to trust new evidence.
"""
from __future__ import annotations

from ..domain.models import ReviewerStats

PRIOR_N = 3
PRIOR_ACCEPT = 0.6
PRIOR_ON_TIME = 0.75
PRIOR_RATING = 3.5

W_ACCEPT, W_ON_TIME, W_RATING = 0.35, 0.40, 0.25


def _smoothed(successes: float, trials: float, prior_rate: float, prior_n: int = PRIOR_N) -> float:
    return (successes + prior_rate * prior_n) / (trials + prior_n)


def reliability_score(s: ReviewerStats) -> float:
    accept = _smoothed(s.accepted, s.invited, PRIOR_ACCEPT)
    on_time = _smoothed(s.on_time, s.completed, PRIOR_ON_TIME)
    rating = _smoothed(s.rating_sum, s.rating_count, PRIOR_RATING) / 5.0
    return W_ACCEPT * accept + W_ON_TIME * on_time + W_RATING * rating
