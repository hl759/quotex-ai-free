from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class RegimeSpecialist(BaseSpecialist):
    name = "regime"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction = None
        reasons = []
        veto = False
        if features.regime == "trend":
            direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
            strength += 0.65
            reasons.append("Regime trend")
        elif features.regime == "mixed":
            direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
            strength += 0.35
            reasons.append("Regime mixed")
        elif features.regime == "sideways":
            strength += 0.15
            reasons.append("Regime sideways")
        elif features.regime == "chaotic":
            veto = True
            reasons.append("Regime chaotic")
        confidence = 84 if features.regime == "chaotic" else int(max(50, min(85, 50 + strength * 12)))
        setup_quality = "fragil" if veto else "favoravel" if strength >= 0.6 else "monitorado"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength), 2), veto, reasons)
