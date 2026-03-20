class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning

    def decide(self, asset, indicators):
        base_score = indicators.get("score", 0)
        direction = indicators.get("direction", "CALL")
        regime = indicators.get("regime", "unknown")

        # 🔹 Aprendizado (inclinação leve)
        boost = self.learning.get_score_boost(asset)
        profile = self.learning.get_calibration_profile(asset)

        adjusted_score = base_score + (boost * 0.7)

        # 🔹 Ajuste por regime (mais humano)
        if regime == "trend":
            adjusted_score += 0.5
        elif regime == "sideways":
            adjusted_score -= 0.3
        elif regime == "mixed":
            adjusted_score -= 0.1

        # 🔹 Aplicar fator de confiança (leve)
        confidence = 50 + (adjusted_score * 10)
        confidence *= profile.get("confidence_factor", 1.0)

        confidence = max(50, min(95, confidence))

        # 🔹 DECISÃO EQUILIBRADA (ESSÊNCIA DOS TRADERS)
        if adjusted_score >= 3.2:
            decision = "ENTRADA_FORTE"
        elif adjusted_score >= 2.4:
            decision = "ENTRADA_CAUTELA"
        elif adjusted_score >= 1.8:
            decision = "OBSERVAR"
        else:
            decision = "NAO_OPERAR"
            direction = None

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": int(confidence),
            "regime": regime,
            "reasons": [
                f"Score base: {base_score}",
                f"Boost aprendizado: {round(boost,2)}",
                f"Regime: {regime}",
                f"Score ajustado: {round(adjusted_score,2)}",
                f"Modo: equilíbrio inteligente"
            ]
        }
