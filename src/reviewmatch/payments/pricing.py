"""How an honorarium is split between reviewer and platform.

The journal sets the gross honorarium. The platform takes a percentage (basis points,
so 1250 = 12.5%) with an optional floor so tiny honoraria still cover processing costs.
Rounding always favours the reviewer: the platform cut is rounded *down*.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Split:
    gross: int
    platform_cut: int
    reviewer_net: int


@dataclass(frozen=True)
class FeePolicy:
    platform_rate_bps: int = 1250      # 12.5%
    min_cut_minor: int = 0             # e.g. 100 = never take less than £1

    def split(self, gross: int) -> Split:
        if gross < 0:
            raise ValueError("gross must be non-negative")
        cut = (gross * self.platform_rate_bps) // 10_000
        cut = max(cut, self.min_cut_minor)
        cut = min(cut, gross)              # never take more than exists
        return Split(gross, cut, gross - cut)
