from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class TrendSpecialist(BaseSpecialist):
    name = "trend"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction = None
        reasons = []
        if features.trend_m1 == "bull":
            direction = "CALL"
            strength += 0.9
            reasons.append("Tendência M1 bullish")
        elif features.trend_m1 == "bear":
            direction = "PUT"
            strength += 0.9
            reasons.append("Tendência M1 bearish")
        if features.trend_m5 == features.trend_m1 and features.trend_m5 in ("bull", "bear"):
            strength += 0.9
            reasons.append("M1 alinhado com M5")
        elif features.trend_m5 in ("bull", "bear") and features.trend_m1 != features.trend_m5:
            strength -= 0.4
            reasons.append("Conflito entre M1 e M5")
        if features.trend_quality_signal == "forte":
            strength += 0.45
            reasons.append("Qualidade estrutural forte")
        elif features.trend_quality_signal == "fragil":
            strength -= 0.45
            reasons.append("Qualidade estrutural frágil")
        if features.late_entry_risk or features.explosive_expansion:
            strength -= 0.45
            reasons.append("Timing ruim para continuidade")
        confidence = int(max(50, min(94, 52 + strength * 14)))
        setup_quality = "premium" if strength >= 1.7 else "favoravel" if strength >= 1.2 else "monitorado" if strength >= 0.75 else "fragil"
        return SpecialistVote(self.name, direction, round(max(0.0, strength), 2), confidence, setup_quality, round(max(0.0, strength) / 2.5, 2), False, reasons)
