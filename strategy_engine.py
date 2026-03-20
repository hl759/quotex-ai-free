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

        if regime not in ("trend", "mixed"):
            return {
                "strategy": "trend",
                "valid": False,
                "score": 0.0,
                "direction": None,
                "confidence": 50,
                "reasons": ["Trend strategy ignorada fora de trend/mixed"]
            }

        if trend_m1 == "bull":
            direction = "CALL"
            score += 1.7
            reasons.append("Tendência M1 bullish")
        elif trend_m1 == "bear":
            direction = "PUT"
            score += 1.7
            reasons.append("Tendência M1 bearish")

        if trend_m5 in ("bull", "bear"):
            if trend_m5 == trend_m1:
                score += 2.1
                reasons.append("M1 alinhado com M5")
            else:
                score -= 0.9
                reasons.append("Conflito entre M1 e M5")

        if direction == "CALL" and rsi <= 46:
            score += 0.8
            reasons.append("Pullback em tendência de alta")
        elif direction == "PUT" and rsi >= 54:
            score += 0.8
            reasons.append("Pullback em tendência de baixa")

        if breakout:
            score += 0.85
            reasons.append("Breakout a favor da tendência")

        if rejection:
            score += 0.35
            reasons.append("Rejeição favorável")

        if volatility:
            score += 0.35
            reasons.append("Volatilidade saudável")

        if moved_fast:
            score -= 0.35
            reasons.append("Preço já andou um pouco")

        if score < 0:
            score = 0

        confidence = int(min(95, max(50, 52 + score * 8)))

        return {
            "strategy": "trend",
            "valid": score >= 1.9 and direction is not None,
            "score": round(score, 2),
            "direction": direction,
            "confidence": confidence,
            "reasons": reasons
        }

    def reversal_strategy(self, asset, indicators):
        score = 0.0
        reasons = []
        direction = None

        regime = indicators.get("regime", "unknown")
        rsi = indicators.get("rsi", 50)
        rejection = indicators.get("rejection", False)
        pattern = indicators.get("pattern")
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        volatility = indicators.get("volatility", False)
        moved_fast = indicators.get("moved_too_fast", False)

        if regime not in ("sideways", "mixed"):
            return {
                "strategy": "reversal",
                "valid": False,
                "score": 0.0,
                "direction": None,
                "confidence": 50,
                "reasons": ["Reversal strategy ignorada fora de sideways/mixed"]
            }

        if rejection:
            score += 1.3
            reasons.append("Rejeição relevante para reversão")

        if rsi <= 35:
            direction = "CALL"
            score += 1.0
            reasons.append("Sobrevenda favorece reversão de alta")
        elif rsi >= 65:
            direction = "PUT"
            score += 1.0
            reasons.append("Sobrecompra favorece reversão de baixa")

        if pattern == "bullish" and direction == "CALL":
            score += 0.8
            reasons.append("Padrão bullish confirma reversão")
        elif pattern == "bearish" and direction == "PUT":
            score += 0.8
            reasons.append("Padrão bearish confirma reversão")

        if regime == "sideways":
            score += 0.55
            reasons.append("Regime sideways favorece reversão")
        elif regime == "mixed":
            score += 0.25
            reasons.append("Regime mixed aceitável para reversão")

        if trend_m1 in ("bull", "bear") and trend_m5 in ("bull", "bear") and trend_m1 == trend_m5:
            score -= 0.45
            reasons.append("Tendência alinhada reduz força da reversão")

        if volatility:
            score += 0.25
            reasons.append("Volatilidade ajuda reversão")

        if moved_fast:
            score -= 0.20
            reasons.append("Preço já andou um pouco")

        if score < 0:
            score = 0

        confidence = int(min(95, max(50, 50 + score * 9)))

        return {
            "strategy": "reversal",
            "valid": score >= 1.8 and direction is not None,
            "score": round(score, 2),
            "direction": direction,
            "confidence": confidence,
            "reasons": reasons
        }

    def scalp_strategy(self, asset, indicators):
        score = 0.0
        reasons = []
        direction = None

        regime = indicators.get("regime", "unknown")
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        rsi = indicators.get("rsi", 50)
        volatility = indicators.get("volatility", False)
        breakout = indicators.get("breakout", False)
        moved_fast = indicators.get("moved_too_fast", False)
        rejection = indicators.get("rejection", False)

        if regime not in ("mixed", "trend"):
            return {
                "strategy": "scalp",
                "valid": False,
                "score": 0.0,
                "direction": None,
                "confidence": 50,
                "reasons": ["Scalp strategy ignorada fora de mixed/trend"]
            }

        if trend_m1 == "bull":
            direction = "CALL"
            score += 1.0
            reasons.append("Micro direção bullish")
        elif trend_m1 == "bear":
            direction = "PUT"
            score += 1.0
            reasons.append("Micro direção bearish")

        if volatility:
            score += 0.9
            reasons.append("Volatilidade favorece scalp")

        if breakout:
            score += 0.7
            reasons.append("Breakout curto aproveitável")

        if rejection:
            score += 0.25
            reasons.append("Rejeição útil para entrada curta")

        if 42 <= rsi <= 58:
            score += 0.2
            reasons.append("RSI neutro operável para scalp")

        if moved_fast:
            score -= 0.45
            reasons.append("Preço já andou um pouco")

        if score < 0:
            score = 0

        confidence = int(min(92, max(50, 50 + score * 8)))

        return {
            "strategy": "scalp",
            "valid": score >= 1.7 and direction is not None,
            "score": round(score, 2),
            "direction": direction,
            "confidence": confidence,
            "reasons": reasons
        }

    def evaluate_all(self, asset, indicators):
        return [
            self.trend_strategy(asset, indicators),
            self.reversal_strategy(asset, indicators),
            self.scalp_strategy(asset, indicators),
        ]
