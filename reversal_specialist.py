from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class ReversalSpecialist(BaseSpecialist):
    name = "reversal"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction = None
        reasons = []
        if features.rejection:
            strength += 0.8
            reasons.append("Rejeição presente")
        if features.rsi <= 37:
            direction = "CALL"
            strength += 0.8
            reasons.append("Sobrevenda")
        elif features.rsi >= 63:
            direction = "PUT"
            strength += 0.8
            reasons.append("Sobrecompra")
        if features.pattern == "bullish" and direction == "CALL":
            strength += 0.5
            reasons.append("Padrão bullish confirmou")
        elif features.pattern == "bearish" and direction == "PUT":
            strength += 0.5
            reasons.append("Padrão bearish confirmou")
        if features.regime == "sideways":
            strength += 0.35
            reasons.append("Regime lateral favorece reversão")
        elif features.regime == "trend":
            strength -= 0.2
            reasons.append("Regime trend enfraquece reversão")
        confidence = int(max(50, min(92, 50 + strength * 14)))
        setup_quality = "premium" if strength >= 1.7 else "favoravel" if strength >= 1.2 else "monitorado" if strength >= 0.8 else "fragil"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength) / 2.4, 2), False, reasons)
