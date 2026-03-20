from strategy_engine import StrategyEngine


class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning
        self.strategy_engine = StrategyEngine()

    def decide(self, asset, indicators):
        base_score = float(indicators.get("score", 0.0))
        base_direction = indicators.get("direction", "CALL")
        regime = indicators.get("regime", "unknown")

        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        rejection = indicators.get("rejection", False)
        breakout = indicators.get("breakout", False)
        pattern = indicators.get("pattern")
        volatility = indicators.get("volatility", False)
        moved_fast = indicators.get("moved_too_fast", False)
        is_sideways = indicators.get("is_sideways", False)
        rsi = indicators.get("rsi", 50)

        reasons = []

        strategy_result = self.strategy_engine.select_best_strategy(asset, indicators)
        strategy_score = float(strategy_result.get("score", 0.0))
        strategy_direction = strategy_result.get("direction")
        strategy_name = strategy_result.get("strategy", "none")

        adjusted_score = base_score
        reasons.append(f"Score base: {base_score}")

        if strategy_result.get("valid", False):
            adjusted_score += strategy_score * 0.55
            reasons.append(f"Estratégia ativa: {strategy_name}")
            reasons.extend(strategy_result.get("reasons", []))
            if strategy_direction:
                base_direction = strategy_direction
        else:
            reasons.append("Nenhuma estratégia forte ativa")

        boost = 0.0
        try:
            boost = self.learning.get_score_boost(asset)
        except Exception:
            boost = 0.0

        adjusted_score += (boost * 0.7)

        try:
            profile = self.learning.get_calibration_profile(asset)
        except Exception:
            profile = {"confidence_factor": 1.0}

        confidence_factor = profile.get("confidence_factor", 1.0)

        if regime == "trend":
            adjusted_score += 0.35
        elif regime == "mixed":
            adjusted_score += 0.10
        elif regime == "sideways":
            adjusted_score -= 0.15
        elif regime == "chaotic":
            adjusted_score -= 1.0

        if trend_m1 == trend_m5:
            adjusted_score += 0.35

        if rejection:
            adjusted_score += 0.20

        if breakout:
            adjusted_score += 0.25

        if pattern in ("bullish", "bearish"):
            adjusted_score += 0.15

        if volatility:
            adjusted_score += 0.12

        if moved_fast:
            adjusted_score -= 0.20

        if is_sideways:
            adjusted_score -= 0.10

        if rsi <= 35 or rsi >= 65:
            adjusted_score += 0.10

        if regime == "chaotic" and adjusted_score < 2.5:
            return {
                "asset": asset,
                "decision": "NAO_OPERAR",
                "direction": None,
                "score": round(adjusted_score, 2),
                "confidence": 50,
                "regime": regime,
                "reasons": reasons
            }

        if adjusted_score >= 3.25:
            decision = "ENTRADA_FORTE"
            direction = base_direction
        elif adjusted_score >= 2.35:
            decision = "ENTRADA_CAUTELA"
            direction = base_direction
        elif adjusted_score >= 1.75:
            decision = "OBSERVAR"
            direction = base_direction
        else:
            decision = "NAO_OPERAR"
            direction = None

        confidence = int(max(50, min(95, (50 + adjusted_score * 10) * confidence_factor)))

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": confidence,
            "regime": regime,
            "reasons": reasons
        }
