class DecisionEngine:
    def __init__(self, learning_engine):
        self.learning = learning_engine

    def decide(self, asset, indicators):
        regime = indicators.get("regime", "unknown")

        if regime == "trend":
            return self._trend_logic(asset, indicators)
        elif regime == "sideways":
            return self._sideways_logic(asset, indicators)
        elif regime == "chaotic":
            return self._chaotic_logic(asset, indicators)
        else:
            return self._mixed_logic(asset, indicators)

    def _trend_logic(self, asset, ind):
        score = 0
        reasons = []

        trend = ind.get("trend_m1")
        rsi = ind.get("rsi", 50)

        if trend in ("bull","bear"):
            score += 2.5
            reasons.append("Seguindo tendência forte")

        if trend == "bull" and rsi < 45:
            score += 1.2
            reasons.append("Pullback em tendência de alta")

        if trend == "bear" and rsi > 55:
            score += 1.2
            reasons.append("Pullback em tendência de baixa")

        return self._final(asset, score, reasons, trend)

    def _sideways_logic(self, asset, ind):
        score = 0
        reasons = []

        rsi = ind.get("rsi", 50)
        rejection = ind.get("rejection", False)

        if rejection:
            score += 1.5
            reasons.append("Rejeição em lateral")

        if rsi > 65:
            score += 1
            reasons.append("Sobrecompra")

        if rsi < 35:
            score += 1
            reasons.append("Sobrevenda")

        return self._final(asset, score, reasons, None)

    def _chaotic_logic(self, asset, ind):
        return {
            "asset": asset,
            "decision": "NAO_OPERAR",
            "direction": None,
            "score": 0,
            "confidence": 55,
            "reasons": ["Mercado caótico"],
            "regime": "chaotic"
        }

    def _mixed_logic(self, asset, ind):
        score = 1.5
        reasons = ["Mercado misto"]

        return self._final(asset, score, reasons, None)

    def _final(self, asset, score, reasons, trend):
        decision = "ENTRADA_CAUTELA" if score >= 3 else "NAO_OPERAR"
        direction = "CALL" if trend == "bull" else "PUT" if trend == "bear" else None

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(score,2),
            "confidence": int(55 + score*10),
            "reasons": reasons,
            "regime": "auto"
        }
