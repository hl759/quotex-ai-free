from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote

class BaseSpecialist:
    name = "base"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        raise NotImplementedError
