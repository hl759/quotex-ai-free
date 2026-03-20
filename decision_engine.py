from strategy_engine import StrategyEngine


class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning
        self.strategy_engine = StrategyEngine()

    def _build_base_score(self, indicators):
        score = 0.0
        reasons = []

        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        regime = indicators.get("regime", "unknown")
        rsi = indicators.get("rsi", 50)
        breakout = indicators.get("breakout", False)
        rejection = indicators.get("rejection", False)
        volatility = indicators.get("volatility", False)
        moved_fast = indicators.get("moved_too_fast", False)
        is_sideways = indicators.get("is_sideways", False)
        pattern = indicators.get("pattern")

        if trend_m1 in ("bull", "bear"):
            score += 1.0
            reasons.append("Tendência M1 definida")

        if trend_m5 in ("bull", "bear"):
            if trend_m5 == trend_m1:
                score += 0.9
                reasons.append("M1 e M5 alinhados")
            else:
                score -= 0.4
                reasons.append("Conflito entre M1 e M5")

        if breakout:
            score += 0.45
            reasons.append("Breakout limpo")

        if rejection:
            score += 0.35
            reasons.append("Rejeição relevante")

        if pattern in ("bullish", "bearish"):
            score += 0.25
            reasons.append(f"Padrão {pattern}")

        if volatility:
            score += 0.25
            reasons.append("Volatilidade saudável")

        if regime == "trend":
            score += 0.35
            reasons.append("Regime trend favorável")
        elif regime == "mixed":
            score += 0.15
            reasons.append("Regime mixed operável")
        elif regime == "sideways":
            score += 0.05
            reasons.append("Regime sideways tratável")
        elif regime == "chaotic":
            score -= 0.8
            reasons.append("Regime chaotic bloqueando")

        if rsi <= 35 or rsi >= 65:
            score += 0.10
            reasons.append("RSI em zona útil")
        elif 45 <= rsi <= 55:
            score -= 0.03
            reasons.append("RSI neutro")

        if moved_fast:
            score -= 0.18
            reasons.append("Preço já andou um pouco")

        if is_sideways:
            score -= 0.05
            reasons.append("Zona de ruído")

        if score < 0:
            score = 0.0

        return round(score, 2), reasons

    def _vote_direction(self, strategies, fallback_direction):
        votes = {"CALL": 0.0, "PUT": 0.0}
        for s in strategies:
            if not s.get("valid"):
                continue
            direction = s.get("direction")
            if direction in votes:
                votes[direction] += float(s.get("score", 0.0))
        if votes["CALL"] == 0 and votes["PUT"] == 0:
            return fallback_direction
        return "CALL" if votes["CALL"] >= votes["PUT"] else "PUT"

    def _weight_by_regime(self, strategy_name, regime):
        if regime == "trend":
            if strategy_name == "trend":
                return 0.62
            if strategy_name == "scalp":
                return 0.28
            if strategy_name == "reversal":
                return 0.20

        if regime == "sideways":
            if strategy_name == "reversal":
                return 0.62
            if strategy_name == "scalp":
                return 0.25
            if strategy_name == "trend":
                return 0.18

        if regime == "mixed":
            if strategy_name == "trend":
                return 0.48
            if strategy_name == "reversal":
                return 0.36
            if strategy_name == "scalp":
                return 0.34

        return 0.35

    def decide(self, asset, indicators):
        regime = indicators.get("regime", "unknown")
        fallback_direction = indicators.get("direction", "CALL")

        base_score, base_reasons = self._build_base_score(indicators)
        reasons = [f"Score base: {base_score}"]
        reasons.extend(base_reasons)

        strategies = self.strategy_engine.evaluate_all(asset, indicators)
        valid_strategies = [s for s in strategies if s.get("valid")]
        valid_strategies.sort(key=lambda x: (x.get("score", 0), x.get("confidence", 0)), reverse=True)

        adjusted_score = float(base_score)

        if valid_strategies:
            fusion_total = 0.0
            used = []
            for s in valid_strategies[:3]:
                weight = self._weight_by_regime(s.get("strategy", "none"), regime)
                fusion_total += float(s.get("score", 0.0)) * weight
                used.append(s.get("strategy", "none"))

            adjusted_score += fusion_total

            if len(used) == 1:
                reasons.append(f"Estratégia líder: {used[0]}")
            else:
                reasons.append(f"Fusão estratégica ativa: {', '.join(used)}")

            leader = valid_strategies[0]
            reasons.extend(leader.get("reasons", []))
            reasons.append(f"Estratégias válidas: {len(valid_strategies)}")
        else:
            reasons.append("Nenhuma estratégia forte ativa")

        final_direction = self._vote_direction(valid_strategies, fallback_direction)

        boost = 0.0
        try:
            boost = self.learning.get_score_boost(asset)
        except Exception:
            boost = 0.0

        adjusted_score += (boost * 0.65)
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

        if regime == "chaotic" and adjusted_score < 2.4:
            confidence = max(50, min(95, int((50 + adjusted_score * 10) * confidence_factor)))
            reasons.append(f"Regime final: {regime}")
            reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
            reasons.append("Modo: v11 etapa 4 refinado")
            return {
                "asset": asset,
                "decision": "NAO_OPERAR",
                "direction": None,
                "score": round(adjusted_score, 2),
                "confidence": confidence,
                "regime": regime,
                "reasons": reasons
            }

        consensus_bonus = 0.0
        if len(valid_strategies) >= 2:
            top1 = valid_strategies[0]
            top2 = valid_strategies[1]
            same_direction = top1.get("direction") == top2.get("direction")
            both_strong = float(top1.get("score", 0.0)) >= 2.5 and float(top2.get("score", 0.0)) >= 2.0

            if same_direction and both_strong:
                consensus_bonus = 0.22
                adjusted_score += consensus_bonus
                reasons.append("Consenso forte entre estratégias")
            elif same_direction:
                consensus_bonus = 0.10
                adjusted_score += consensus_bonus
                reasons.append("Consenso leve entre estratégias")

        if adjusted_score >= 3.35:
            decision = "ENTRADA_FORTE"
            direction = final_direction
        elif adjusted_score >= 2.30:
            decision = "ENTRADA_CAUTELA"
            direction = final_direction
        elif adjusted_score >= 1.70:
            promote_to_caution = False
            if regime == "trend" and any(s.get("strategy") == "trend" and s.get("valid") for s in valid_strategies):
                promote_to_caution = True
            elif regime == "sideways" and any(s.get("strategy") == "reversal" and s.get("valid") for s in valid_strategies):
                promote_to_caution = True
            elif regime == "mixed" and len(valid_strategies) >= 2:
                promote_to_caution = True

            if promote_to_caution:
                decision = "ENTRADA_CAUTELA"
                direction = final_direction
                reasons.append("OBSERVAR promovido para CAUTELA")
            else:
                decision = "OBSERVAR"
                direction = final_direction
        else:
            decision = "NAO_OPERAR"
            direction = None

        confidence = 50 + (adjusted_score * 10)
        confidence *= confidence_factor
        if consensus_bonus > 0:
            confidence += 2
        confidence = max(50, min(95, confidence))

        leader_name = valid_strategies[0].get("strategy", "none") if valid_strategies else "none"
        leader_score = float(valid_strategies[0].get("score", 0.0)) if valid_strategies else 0.0

        reasons.append(f"Regime final: {regime}")
        reasons.append(f"Estratégia líder: {leader_name}")
        reasons.append(f"Strategy score: {round(leader_score, 2)}")
        reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
        reasons.append("Modo: v11 etapa 4 refinado")

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": int(confidence),
            "regime": regime,
            "reasons": reasons
        }
