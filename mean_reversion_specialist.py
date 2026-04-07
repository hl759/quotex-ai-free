from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class MeanReversionSpecialist(BaseSpecialist):
    name = "mean_reversion"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction = None
        reasons = []
        if features.is_sideways:
            strength += 0.35
            reasons.append("Mercado lateral")
        if features.rsi < 35:
            direction = "CALL"
            strength += 0.55
            reasons.append("Preço esticado para baixo")
        elif features.rsi > 65:
            direction = "PUT"
            strength += 0.55
            reasons.append("Preço esticado para cima")
        if features.rejection:
            strength += 0.3
            reasons.append("Rejeição ajuda retorno à média")
        confidence = int(max(50, min(88, 50 + strength * 12)))
        setup_quality = "favoravel" if strength >= 1.0 else "monitorado" if strength >= 0.6 else "fragil"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength) / 1.7, 2), False, reasons)
