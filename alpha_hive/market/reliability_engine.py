from __future__ import annotations

from typing import List, Tuple

from alpha_hive.core.contracts import Candle

class ReliabilityEngine:
    def evaluate(self, provider: str, chain: List[str], candles: List[Candle], health_score: float) -> Tuple[float, str, List[str]]:
        warnings: List[str] = []
        score = 1.0

        if not candles:
            return 0.0, "unavailable", ["Sem candles disponíveis"]

        if len(candles) < 20:
            score -= 0.25
            warnings.append("Histórico curto")

        if provider != chain[0]:
            score -= 0.18
            warnings.append(f"Fallback ativo: {provider}")

        if "cache" in provider:
            score -= 0.08
            warnings.append("Dados vindos de cache")

        if health_score < 0.45:
            score -= 0.12
            warnings.append("Provider com saúde baixa")
        elif health_score < 0.65:
            score -= 0.06
            warnings.append("Provider com saúde moderada")

        score = max(0.0, min(1.0, round(score, 2)))
        if score >= 0.85:
            state = "high"
        elif score >= 0.68:
            state = "good"
        elif score >= 0.52:
            state = "fragile"
        else:
            state = "poor"
        return score, state, warnings
