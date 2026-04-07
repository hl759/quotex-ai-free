from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class VolatilitySpecialist(BaseSpecialist):
    name = "volatility"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        reasons = []
        veto = False
        if features.volatility:
            strength += 0.45
            reasons.append("Volatilidade presente")
        if features.explosive_expansion:
            strength -= 0.55
            veto = True
            reasons.append("Expansão explosiva pode degradar execução")
        direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
        confidence = int(max(50, min(85, 50 + max(0.0, strength) * 10)))
        setup_quality = "monitorado" if strength >= 0.4 else "fragil"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength) / 1.2, 2), veto, reasons)
