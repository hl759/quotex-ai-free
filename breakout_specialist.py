from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class BreakoutSpecialist(BaseSpecialist):
    name = "breakout"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
        reasons = []
        if features.breakout:
            strength += 0.9 if features.breakout_quality == "strong" else 0.45
            reasons.append(f"Breakout {features.breakout_quality}")
        if features.volatility:
            strength += 0.2
            reasons.append("Volatilidade ajuda rompimento")
        if features.moved_too_fast:
            strength -= 0.25
            reasons.append("Movimento já esticado")
        if not features.breakout:
            direction = None
        confidence = int(max(50, min(92, 50 + strength * 16)))
        setup_quality = "premium" if strength >= 1.3 else "favoravel" if strength >= 0.9 else "monitorado" if strength >= 0.5 else "fragil"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength) / 1.9, 2), False, reasons)
