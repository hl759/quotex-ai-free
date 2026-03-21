from strategy_engine import StrategyEngine
from strategy_lab import StrategyLab
from adaptive_engine import AdaptiveEngine
from memory_engine import MemoryEngine


class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning
        self.strategy_engine = StrategyEngine()
        self.strategy_lab = StrategyLab()
        self.adaptive_engine = AdaptiveEngine()
        self.memory_engine = MemoryEngine()

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
                score -= 0.35
                reasons.append("Conflito entre M1 e M5")

        if breakout:
            score += 0.40
            reasons.append("Breakout limpo")

        if rejection:
            score += 0.32
            reasons.append("Rejeição relevante")

        if pattern in ("bullish", "bearish"):
            score += 0.22
            reasons.append(f"Padrão {pattern}")

        if volatility:
            score += 0.22
            reasons.append("Volatilidade saudável")

        if regime == "trend":
            score += 0.32
            reasons.append("Regime trend favorável")
        elif regime == "mixed":
            score += 0.18
            reasons.append("Regime mixed operável")
        elif regime == "sideways":
            score += 0.10
            reasons.append("Regime sideways tratável")
        elif regime == "chaotic":
            score -= 0.8
            reasons.append("Regime chaotic bloqueando")

        if rsi <= 35 or rsi >= 65:
            score += 0.10
            reasons.append("RSI em zona útil")
        elif 45 <= rsi <= 55:
            score -= 0.02
            reasons.append("RSI neutro")

        if moved_fast:
            score -= 0.16
            reasons.append("Preço já andou um pouco")

        if is_sideways:
            score -= 0.04
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
                return 0.58
            if strategy_name == "scalp":
                return 0.30
            if strategy_name == "reversal":
                return 0.20
        if regime == "sideways":
            if strategy_name == "reversal":
                return 0.58
            if strategy_name == "scalp":
                return 0.28
            if strategy_name == "trend":
                return 0.22
        if regime == "mixed":
            if strategy_name == "trend":
                return 0.46
            if strategy_name == "reversal":
                return 0.38
            if strategy_name == "scalp":
                return 0.36
        return 0.35

    def decide(self, asset, indicators):
        regime = indicators.get("regime", "unknown")
        fallback_direction = indicators.get("direction", "CALL")
        analysis_time = indicators.get("analysis_time")

        base_score, base_reasons = self._build_base_score(indicators)
        reasons = [f"Score base: {base_score}"]
        reasons.extend(base_reasons)

        strategies = self.strategy_engine.evaluate_all(asset, indicators)
        valid_strategies = [s for s in strategies if s.get("valid")]
        valid_strategies.sort(key=lambda x: (x.get("score", 0), x.get("confidence", 0)), reverse=True)

        adjusted_score = float(base_score)
        leader_setup_id = None
        leader_context_id = None
        leader_name = "none"
        leader_score = 0.0
        filtered = []

        if valid_strategies:
            fusion_total = 0.0
            used = []

            for s in valid_strategies[:3]:
                strategy_name = s.get("strategy", "none")

                if self.adaptive_engine.should_soft_block(strategy_name, regime):
                    filtered.append(strategy_name)
                    reasons.append(f"Estratégia temporariamente enfraquecida: {strategy_name}")
                    continue

                base_weight = self._weight_by_regime(strategy_name, regime)
                adaptive_weight = self.adaptive_engine.get_weight(strategy_name, regime)
                final_weight = base_weight * adaptive_weight
                fusion_total += float(s.get("score", 0.0)) * final_weight
                used.append(strategy_name)

            adjusted_score += fusion_total

            if used:
                if len(used) == 1:
                    reasons.append(f"Estratégia líder: {used[0]}")
                else:
                    reasons.append(f"Fusão estratégica ativa: {', '.join(used)}")
            else:
                reasons.append("Estratégias válidas sem força operacional suficiente")

            leader = None
            for candidate in valid_strategies:
                c_name = candidate.get("strategy", "none")
                if c_name not in filtered:
                    leader = candidate
                    break

            if leader is None and valid_strategies:
                leader = valid_strategies[0]

            if leader is not None:
                leader_name = leader.get("strategy", "none")
                leader_score = float(leader.get("score", 0.0))
                reasons.extend(leader.get("reasons", []))

            reasons.append(f"Estratégias válidas: {len(valid_strategies)}")

            if leader_name != "none":
                leader_setup_id = self.strategy_lab.register_setup(
                    asset=asset,
                    strategy_name=leader_name,
                    indicators=indicators,
                    signal=leader.get("direction"),
                    analysis_time=analysis_time,
                )
                setup_boost, setup_reason = self.strategy_lab.get_setup_boost(leader_setup_id)
                adjusted_score += setup_boost
                reasons.append(setup_reason)
                reasons.append(self.adaptive_engine.get_reason(leader_name, regime))

                leader_context_id = self.memory_engine.register_context(
                    asset=asset,
                    strategy_name=leader_name,
                    indicators=indicators,
                    analysis_time=analysis_time,
                )
                memory_boost, memory_reason = self.memory_engine.get_memory_boost(leader_context_id)
                adjusted_score += memory_boost
                reasons.append(memory_reason)
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

        if regime == "chaotic" and adjusted_score < 2.3:
            confidence = max(50, min(95, int((50 + adjusted_score * 10) * confidence_factor)))
            reasons.append(f"Regime final: {regime}")
            reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
            reasons.append("Modo: v12 etapa 4 memória inteligente")
            return {
                "asset": asset,
                "decision": "NAO_OPERAR",
                "direction": None,
                "score": round(adjusted_score, 2),
                "confidence": confidence,
                "regime": regime,
                "reasons": reasons,
                "setup_id": leader_setup_id,
                "context_id": leader_context_id,
                "strategy_name": leader_name
            }

        consensus_bonus = 0.0
        if len(valid_strategies) >= 2:
            active = [s for s in valid_strategies if s.get("strategy") not in filtered]
            if len(active) >= 2:
                top1 = active[0]
                top2 = active[1]
                same_direction = top1.get("direction") == top2.get("direction")
                both_strong = float(top1.get("score", 0.0)) >= 2.0 and float(top2.get("score", 0.0)) >= 1.6

                if same_direction and both_strong:
                    consensus_bonus = 0.20
                    adjusted_score += consensus_bonus
                    reasons.append("Consenso forte entre estratégias")
                elif same_direction:
                    consensus_bonus = 0.10
                    adjusted_score += consensus_bonus
                    reasons.append("Consenso leve entre estratégias")

        if adjusted_score >= 3.10:
            decision = "ENTRADA_FORTE"
            direction = final_direction
        elif adjusted_score >= 2.00:
            decision = "ENTRADA_CAUTELA"
            direction = final_direction
        elif adjusted_score >= 1.40:
            promote_to_caution = False
            active_names = [s.get("strategy") for s in valid_strategies if s.get("strategy") not in filtered]

            if regime == "trend" and "trend" in active_names:
                promote_to_caution = True
            elif regime == "sideways" and any(x in active_names for x in ("reversal", "scalp")):
                promote_to_caution = True
            elif regime == "mixed" and len(active_names) >= 1:
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

        reasons.append(f"Regime final: {regime}")
        reasons.append(f"Estratégia líder: {leader_name}")
        reasons.append(f"Strategy score: {round(leader_score, 2)}")
        reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
        reasons.append("Modo: v12 etapa 4 memória inteligente")

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": int(confidence),
            "regime": regime,
            "reasons": reasons,
            "setup_id": leader_setup_id,
            "context_id": leader_context_id,
            "strategy_name": leader_name
        }
