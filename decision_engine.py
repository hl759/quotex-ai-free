class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning

    def decide(self, asset, indicators):
        base_score = indicators.get("score", 0)
        boost = self.learning.get_score_boost(asset)

        final_score = base_score + boost

        confidence = min(95, max(50, 50 + final_score * 10))

        if final_score > 3:
            decision = "ENTRADA_FORTE"
            direction = indicators.get("direction", "CALL")
        elif final_score > 2:
            decision = "ENTRADA_CAUTELA"
            direction = indicators.get("direction", "CALL")
        else:
            decision = "NAO_OPERAR"
            direction = None

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(final_score,2),
            "confidence": int(confidence),
            "regime": indicators.get("regime","unknown"),
            "reasons": [
                f"Score base: {base_score}",
                f"Ajuste aprendizado: {round(boost,2)}",
                f"Score final: {round(final_score,2)}"
            ]
        }
