from __future__ import annotations

from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class SessionSpecialist(BaseSpecialist):
    name = "session"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        hour = now_brazil().hour
        strength = 0.4
        reasons = []
        if snapshot.market_type == "crypto":
            strength += 0.2
            reasons.append("Cripto é 24h")
        if 7 <= hour <= 11 or 14 <= hour <= 18:
            strength += 0.2
            reasons.append("Janela de liquidez melhor")
        else:
            reasons.append("Janela neutra")
        direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
        confidence = int(max(50, min(80, 50 + strength * 10)))
        setup_quality = "favoravel" if strength >= 0.6 else "monitorado"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength), 2), False, reasons)
