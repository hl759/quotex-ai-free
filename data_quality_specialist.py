from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

class DataQualitySpecialist(BaseSpecialist):
    name = "data_quality"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        score = snapshot.data_quality_score
        reasons = [*snapshot.warnings] if snapshot.warnings else ["Dados sem alertas"]
        veto = score < 0.45
        if score >= 0.85:
            setup_quality = "premium"
        elif score >= 0.70:
            setup_quality = "favoravel"
        elif score >= 0.55:
            setup_quality = "monitorado"
        else:
            setup_quality = "fragil"
        direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
        return SpecialistVote(self.name, direction, round(score, 2), int(50 + score * 40), setup_quality, round(score, 2), veto, reasons)
