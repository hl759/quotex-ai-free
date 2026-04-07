from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class TimingSpecialist(BaseSpecialist):
    name = "timing"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.7
        reasons = ["Timing base operável"]
        veto = False
        if features.late_entry_risk:
            strength -= 0.7
            veto = True
            reasons.append("Late entry risk alto")
        if features.moved_too_fast:
            strength -= 0.35
            reasons.append("Movimento já correu")
        direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
        confidence = int(max(50, min(90, 50 + max(0.0, strength) * 16)))
        setup_quality = "fragil" if strength < 0.25 else "monitorado" if strength < 0.75 else "favoravel"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength), 2), veto, reasons)
