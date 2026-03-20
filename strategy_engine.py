class StrategyEngine:
    def __init__(self):
        pass

    def trend_strategy(self, asset, indicators):
        score = 0.0
        reasons = []
        direction = None

        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        rsi = indicators.get("rsi", 50)
        breakout = indicators.get("breakout", False)
        rejection = indicators.get("rejection", False)
        volatility = indicators.get("volatility", False)
        regime = indicators.get("regime", "unknown")
        moved_fast = indicators.get("moved_too_fast", False)

        # Estratégia só faz sentido em trend ou mixed
        if regime not in ("trend", "mixed"):
            return {
                "strategy": "trend",
                "valid": False,
                "score": 0.0,
                "direction": None,
                "confidence": 50,
                "reasons": ["Trend strategy ignorada fora de trend/mixed"]
            }

        # Direção principal
        if trend_m1 == "bull":
            direction = "CALL"
            score += 1.6
            reasons.append("Tendência M1 bullish")
        elif trend_m1 == "bear":
            direction = "PUT"
            score += 1.6
            reasons.append("Tendência M1 bearish")

        # Confirmação estrutural
        if trend_m5 in ("bull", "bear"):
            if trend_m5 == trend_m1:
                score += 2.0
                reasons.append("M1 alinhado com M5")
            else:
                score -= 0.9
                reasons.append("Conflito entre M1 e M5")

        # Pullback saudável em tendência
        if direction == "CALL" and rsi <= 45:
            score += 0.8
            reasons.append("Pullback em tendência de alta")
        elif direction == "PUT" and rsi >= 55:
            score += 0.8
            reasons.append("Pullback em tendência de baixa")

        # Continuação
        if breakout:
            score += 0.8
            reasons.append("Breakout a favor da tendência")

        if rejection:
            score += 0.4
            reasons.append("Rejeição favorável")

        if volatility:
            score += 0.3
            reasons.append("Volatilidade saudável")

        if moved_fast:
            score -= 0.4
            reasons.append("Preço já andou um pouco")

        if score < 0:
            score = 0

        confidence = int(min(95, max(50, 52 + score * 8)))

        return {
            "strategy": "trend",
            "valid": score >= 1.8 and direction is not None,
            "score": round(score, 2),
            "direction": direction,
            "confidence": confidence,
            "reasons": reasons
        }

    def select_best_strategy(self, asset, indicators):
        trend_result = self.trend_strategy(asset, indicators)

        if trend_result["valid"]:
            return trend_result

        return {
            "strategy": "none",
            "valid": False,
            "score": 0.0,
            "direction": None,
            "confidence": 50,
            "reasons": ["Nenhuma estratégia válida no momento"]
      }
