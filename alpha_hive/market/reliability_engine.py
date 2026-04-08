from __future__ import annotations

from typing import List, Tuple

from alpha_hive.core.contracts import Candle


class ReliabilityEngine:
    def evaluate(self, provider: str, chain: List[str], candles: List[Candle], health_score: float) -> Tuple[float, str, List[str]]:
        warnings: List[str] = []
        score = 1.0

        if not candles:
            return 0.0, "unavailable", ["Sem candles disponíveis"]

        provider = str(provider or "unknown")
        provider_root = provider.split("-")[0]
        chain_root = chain[0] if chain else "unknown"

        if len(candles) < 20:
            score -= 0.25
            warnings.append("Histórico curto")

        if provider_root != chain_root:
            score -= 0.12
            warnings.append(f"Fallback real ativo: {provider}")

        if "cache" in provider:
            score -= 0.05
            warnings.append("Dados vindos de cache")

        if health_score < 0.45:
            score -= 0.10
            warnings.append("Provider com saúde baixa")
        elif health_score < 0.65:
            score -= 0.04
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
