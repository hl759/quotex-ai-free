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
            adjusted_score += strategy_score * 0.60
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
        reasons.append(f"Boost aprendizado: {round(boost, 2)}")

        try:
            profile = self.learning.get_calibration_profile(asset)
        except Exception:
            profile = {
                "confidence_factor": 1.0,
                "aggressiveness": 1.0,
                "min_score": 3.0,
                "max_signals": 2,
                "mode": "base"
            }

        confidence_factor = profile.get("confidence_factor", 1.0)

        if regime == "trend":
            adjusted_score += 0.35
            reasons.append("Regime trend favorável")
        elif regime == "mixed":
            adjusted_score += 0.12
            reasons.append("Regime mixed operável")
        elif regime == "sideways":
            adjusted_score -= 0.05
            reasons.append("Regime sideways com reversão possível")
        elif regime == "chaotic":
            adjusted_score -= 1.0
            reasons.append("Regime chaotic bloqueando")

        if trend_m1 in ("bull", "bear") and trend_m5 in ("bull", "bear"):
            if trend_m1 == trend_m5:
                adjusted_score += 0.25
                reasons.append("M1 e M5 alinhados")
            else:
                adjusted_score -= 0.15
                reasons.append("Conflito entre M1 e M5")

        if rejection:
            adjusted_score += 0.20
            reasons.append("Rejeição relevante")

        if breakout:
            adjusted_score += 0.20
            reasons.append("Breakout limpo")

        if pattern in ("bullish", "bearish"):
            adjusted_score += 0.10
            reasons.append(f"Padrão {pattern}")

        if volatility:
            adjusted_score += 0.10
            reasons.append("Volatilidade saudável")

        if moved_fast:
            adjusted_score -= 0.18
            reasons.append("Preço já andou um pouco")

        if is_sideways:
            adjusted_score -= 0.05
            reasons.append("Zona de ruído")

        if rsi <= 35 or rsi >= 65:
            adjusted_score += 0.08
            reasons.append("RSI em zona útil")
        elif 45 <= rsi <= 55:
            adjusted_score -= 0.03
            reasons.append("RSI neutro")

        if regime == "chaotic" and adjusted_score < 2.4:
            decision = "NAO_OPERAR"
            confidence = max(50, min(95, int((50 + adjusted_score * 10) * confidence_factor)))
            reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
            reasons.append("Modo: proteção em caos")
            return {
                "asset": asset,
                "decision": decision,
                "direction": None,
                "score": round(adjusted_score, 2),
                "confidence": confidence,
                "regime": regime,
                "reasons": reasons
            }

        if adjusted_score >= 3.20:
            decision = "ENTRADA_FORTE"
            direction = base_direction
        elif adjusted_score >= 2.25:
            decision = "ENTRADA_CAUTELA"
            direction = base_direction
        elif adjusted_score >= 1.65:
            promote_to_caution = False

            if regime == "trend":
                if breakout or rejection or trend_m1 == trend_m5 or strategy_result.get("valid", False):
                    promote_to_caution = True
            elif regime == "mixed":
                if breakout or rejection or pattern in ("bullish", "bearish") or strategy_name == "reversal":
                    promote_to_caution = True
            elif regime == "sideways":
                if strategy_name == "reversal" and rejection:
                    promote_to_caution = True

            if promote_to_caution:
                decision = "ENTRADA_CAUTELA"
                direction = base_direction
                reasons.append("OBSERVAR promovido para CAUTELA")
            else:
                decision = "OBSERVAR"
                direction = base_direction
        else:
            decision = "NAO_OPERAR"
            direction = None

        confidence = 50 + (adjusted_score * 10)
        confidence *= confidence_factor
        confidence = max(50, min(95, confidence))

        reasons.append(f"Regime final: {regime}")
        reasons.append(f"Strategy score: {round(strategy_score, 2)}")
        reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
        reasons.append("Modo: v11 etapa 2 integrada")

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": int(confidence),
            "regime": regime,
            "reasons": reasons
        }
