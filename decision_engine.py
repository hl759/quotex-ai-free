from strategy_engine import StrategyEngine
from meta_context_reasoning_engine import MetaContextReasoningEngine

try:
    from strategy_variants_engine import StrategyVariantsEngine
except Exception:
    StrategyVariantsEngine = None

try:
    from strategy_lab import StrategyLab
except Exception:
    class StrategyLab:
        def register_setup(self, *args, **kwargs): return None
        def get_setup_boost(self, *args, **kwargs): return (0.0, "Strategy Lab neutro")

try:
    from adaptive_engine import AdaptiveEngine
except Exception:
    class AdaptiveEngine:
        def get_weight(self, *args, **kwargs): return 1.0
        def get_reason(self, *args, **kwargs): return "Peso adaptativo neutro"
        def should_soft_block(self, *args, **kwargs): return False

try:
    from memory_engine import MemoryEngine
except Exception:
    class MemoryEngine:
        def register_context(self, *args, **kwargs): return None
        def get_memory_boost(self, *args, **kwargs): return (0.0, "Memória neutra")

try:
    from market_profile_engine import MarketProfileEngine
except Exception:
    class MarketProfileEngine:
        def get_profile(self, *args, **kwargs): return {"mode": "neutral", "score_shift": 0.0, "consensus_bonus": 0.0, "confidence_shift": 0, "reason": "Mercado em equilíbrio"}

try:
    from strategy_evolution_engine import StrategyEvolutionEngine
except Exception:
    class StrategyEvolutionEngine:
        def get_adjustment(self, *args, **kwargs): return {"boost": 0.0, "reason": "Evolução neutra", "variant": "base"}

try:
    from capital_mind_engine import CapitalMindEngine
except Exception:
    class CapitalMindEngine:
        def get_plan(self, *args, **kwargs): return {"phase": "neutral", "risk_pct": 0.0, "stake_value": 0.0, "score_shift": 0.0, "confidence_shift": 0, "reason": "Capital Mind neutro", "target_value": 0.0, "stop_value": 0.0}

try:
    from context_intelligence_engine import ContextIntelligenceEngine
except Exception:
    class ContextIntelligenceEngine:
        def get_adjustment(self, *args, **kwargs): return {"score_boost": 0.0, "confidence_shift": 0, "reason": "Contexto neutro", "mode": "neutral"}

try:
    from context_pattern_intelligence_engine import ContextPatternIntelligenceEngine
except Exception:
    class ContextPatternIntelligenceEngine:
        def get_adjustment(self, *args, **kwargs): return {"score_boost": 0.0, "confidence_shift": 0, "reason": "Context Pattern neutro", "mode": "neutral"}


class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning
        self.strategy_engine = StrategyEngine()
        self.variants_engine = StrategyVariantsEngine() if StrategyVariantsEngine else None
        self.strategy_lab = StrategyLab()
        self.adaptive_engine = AdaptiveEngine()
        self.memory_engine = MemoryEngine()
        self.market_profile_engine = MarketProfileEngine()
        self.strategy_evolution_engine = StrategyEvolutionEngine()
        self.capital_mind_engine = CapitalMindEngine()
        self.context_intelligence_engine = ContextIntelligenceEngine()
        self.context_pattern_engine = ContextPatternIntelligenceEngine()
        self.meta_context_engine = MetaContextReasoningEngine()

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
            score += 1.0; reasons.append("Tendência M1 definida")
        if trend_m5 in ("bull", "bear"):
            if trend_m5 == trend_m1:
                score += 0.9; reasons.append("M1 e M5 alinhados")
            else:
                score -= 0.35; reasons.append("Conflito entre M1 e M5")
        if breakout:
            score += 0.40; reasons.append("Breakout limpo")
        if rejection:
            score += 0.32; reasons.append("Rejeição relevante")
        if pattern in ("bullish", "bearish"):
            score += 0.22; reasons.append(f"Padrão {pattern}")
        if volatility:
            score += 0.22; reasons.append("Volatilidade saudável")
        if regime == "trend":
            score += 0.32; reasons.append("Regime trend favorável")
        elif regime == "mixed":
            score += 0.18; reasons.append("Regime mixed operável")
        elif regime == "sideways":
            score += 0.10; reasons.append("Regime sideways tratável")
        elif regime == "chaotic":
            score -= 0.8; reasons.append("Regime chaotic bloqueando")
        if rsi <= 35 or rsi >= 65:
            score += 0.10; reasons.append("RSI em zona útil")
        elif 45 <= rsi <= 55:
            score -= 0.02; reasons.append("RSI neutro")
        if moved_fast:
            score -= 0.16; reasons.append("Preço já andou um pouco")
        if is_sideways:
            score -= 0.04; reasons.append("Zona de ruído")
        return round(max(0.0, score), 2), reasons

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
        text = str(strategy_name)
        family = "trend" if text.startswith("trend") else "reversal" if text.startswith("reversal") else "scalp" if text.startswith("scalp") else "other"
        if regime == "trend":
            return {"trend": 0.58, "scalp": 0.30, "reversal": 0.20}.get(family, 0.35)
        if regime == "sideways":
            return {"reversal": 0.58, "scalp": 0.28, "trend": 0.22}.get(family, 0.35)
        if regime == "mixed":
            return {"trend": 0.46, "reversal": 0.38, "scalp": 0.36}.get(family, 0.35)
        return 0.35

    def _expand_candidates(self, asset, indicators, base_candidates):
        if self.variants_engine:
            try:
                return self.variants_engine.expand(asset, indicators, base_candidates)
            except Exception:
                pass
        return [s for s in base_candidates if s.get("valid")]

    def decide(self, asset, indicators):
        regime = indicators.get("regime", "unknown")
        fallback_direction = indicators.get("direction", "CALL")
        analysis_time = indicators.get("analysis_time")
        weekday = indicators.get("weekday")

        market_profile = self.market_profile_engine.get_profile(regime)
        context_adj = self.context_intelligence_engine.get_adjustment(asset=asset, regime=regime, analysis_time=analysis_time, weekday=weekday)

        base_score, base_reasons = self._build_base_score(indicators)
        reasons = [f"Score base: {base_score}"] + base_reasons + [market_profile.get("reason", "Mercado em equilíbrio"), context_adj.get("reason", "Contexto neutro")]

        base_candidates = [s for s in self.strategy_engine.evaluate_all(asset, indicators) if s.get("valid")]
        candidates = self._expand_candidates(asset, indicators, base_candidates)

        adjusted_score = float(base_score) + context_adj.get("score_boost", 0.0)
        leader_setup_id = None
        leader_context_id = None
        leader_name = "none"
        leader_score = 0.0
        evolution_variant = "base"
        filtered = []
        pattern_conf_shift = 0
        pattern_mode = "neutral"
        meta_conf_shift = 0
        meta_data = {"market_narrative": "none", "trend_quality": "neutra", "breakout_quality": "ausente", "conflict_type": "neutro"}

        if candidates:
            fusion_total = 0.0
            used = []
            for s in candidates[:4]:
                strategy_name = s.get("strategy", "none")
                if self.adaptive_engine.should_soft_block(strategy_name, regime):
                    filtered.append(strategy_name)
                    reasons.append(f"Estratégia temporariamente enfraquecida: {strategy_name}")
                    continue
                pattern_adj = self.context_pattern_engine.get_adjustment(asset=asset, regime=regime, strategy_name=strategy_name, analysis_time=analysis_time)
                final_weight = self._weight_by_regime(strategy_name, regime) * self.adaptive_engine.get_weight(strategy_name, regime)
                fusion_total += (float(s.get("score", 0.0)) + pattern_adj.get("score_boost", 0.0)) * final_weight
                used.append(strategy_name)
            adjusted_score += fusion_total
            reasons.append(f"Contextos em competição: {', '.join(used[:3])}" if len(used) > 1 else (f"Estratégia líder: {used[0]}" if used else "Estratégias válidas sem força operacional suficiente"))

            leader = next((c for c in candidates if c.get("strategy") not in filtered), candidates[0])
            leader_name = leader.get("strategy", "none")
            leader_score = float(leader.get("score", 0.0))
            reasons.extend(leader.get("reasons", []))
            reasons.append(f"Estratégias válidas: {len(candidates)}")

            pattern_adj = self.context_pattern_engine.get_adjustment(asset=asset, regime=regime, strategy_name=leader_name, analysis_time=analysis_time)
            adjusted_score += pattern_adj.get("score_boost", 0.0)
            reasons.append(pattern_adj.get("reason", "Context Pattern neutro"))
            pattern_conf_shift = pattern_adj.get("confidence_shift", 0)
            pattern_mode = pattern_adj.get("mode", "neutral")

            meta_adj = self.meta_context_engine.get_adjustment(asset=asset, strategy_name=leader_name, indicators=indicators, analysis_time=analysis_time)
            adjusted_score += meta_adj.get("score_boost", 0.0)
            meta_conf_shift = meta_adj.get("confidence_shift", 0)
            meta_data = meta_adj.get("meta_context", meta_data)
            reasons.extend(meta_adj.get("reasons", []))

            if leader_name != "none":
                leader_setup_id = self.strategy_lab.register_setup(asset=asset, strategy_name=leader_name, indicators=indicators, signal=leader.get("direction"), analysis_time=analysis_time)
                setup_boost, setup_reason = self.strategy_lab.get_setup_boost(leader_setup_id)
                adjusted_score += setup_boost
                reasons.append(setup_reason)
                reasons.append(self.adaptive_engine.get_reason(leader_name, regime))
                leader_context_id = self.memory_engine.register_context(asset=asset, strategy_name=leader_name, indicators=indicators, analysis_time=analysis_time)
                memory_boost, memory_reason = self.memory_engine.get_memory_boost(leader_context_id)
                adjusted_score += memory_boost
                reasons.append(memory_reason)
                evo = self.strategy_evolution_engine.get_adjustment(asset, leader_name, indicators)
                adjusted_score += evo.get("boost", 0.0)
                evolution_variant = evo.get("variant", "base")
                reasons.append(evo.get("reason", "Evolução neutra"))
        else:
            reasons.append("Nenhuma estratégia forte ativa")

        final_direction = self._vote_direction(candidates, fallback_direction)

        try:
            boost = self.learning.get_score_boost(asset)
        except Exception:
            boost = 0.0
        adjusted_score += (boost * 0.65)
        adjusted_score -= market_profile.get("score_shift", 0.0)
        reasons.append(f"Boost aprendizado: {round(boost, 2)}")

        try:
            profile = self.learning.get_calibration_profile(asset)
            confidence_factor = profile.get("confidence_factor", 1.0)
        except Exception:
            confidence_factor = 1.0

        consensus_bonus = 0.0
        active = [s for s in candidates if s.get("strategy") not in filtered]
        if len(active) >= 2:
            top1, top2 = active[0], active[1]
            if top1.get("direction") == top2.get("direction"):
                if float(top1.get("score", 0.0)) >= 2.0 and float(top2.get("score", 0.0)) >= 1.6:
                    consensus_bonus = 0.20 + market_profile.get("consensus_bonus", 0.0)
                    reasons.append("Consenso forte entre contextos")
                else:
                    consensus_bonus = 0.10 + market_profile.get("consensus_bonus", 0.0)
                    reasons.append("Consenso leve entre contextos")
                adjusted_score += consensus_bonus

        base_confidence = 50 + (adjusted_score * 10)
        base_confidence *= confidence_factor
        base_confidence += market_profile.get("confidence_shift", 0)
        base_confidence += context_adj.get("confidence_shift", 0)
        base_confidence += pattern_conf_shift
        base_confidence += meta_conf_shift
        if consensus_bonus > 0:
            base_confidence += 2
        base_confidence = int(max(50, min(95, base_confidence)))

        capital_plan = self.capital_mind_engine.get_plan(asset=asset, adjusted_score=adjusted_score, confidence=base_confidence, indicators=indicators)
        adjusted_score += capital_plan.get("score_shift", 0.0)
        reasons.append(capital_plan.get("reason", "Capital Mind neutro"))

        if regime == "chaotic" and adjusted_score < 2.3:
            decision, direction = "NAO_OPERAR", None
        elif adjusted_score >= 3.00:
            decision, direction = "ENTRADA_FORTE", final_direction
        elif adjusted_score >= 1.90:
            decision, direction = "ENTRADA_CAUTELA", final_direction
        elif adjusted_score >= 1.30:
            promote = len(active) >= 1 and market_profile.get("mode") != "defensive"
            if evolution_variant == "promovida" and final_direction:
                promote = True
            if capital_plan.get("phase") == "defensive":
                promote = False
            if promote:
                decision, direction = "ENTRADA_CAUTELA", final_direction
                reasons.append("OBSERVAR promovido para CAUTELA")
            else:
                decision, direction = "OBSERVAR", final_direction
        else:
            decision, direction = "NAO_OPERAR", None

        confidence = base_confidence + capital_plan.get("confidence_shift", 0)
        confidence = int(max(50, min(95, confidence)))

        reasons.extend([
            f"Regime final: {regime}",
            f"Perfil de mercado: {market_profile.get('mode', 'neutral')}",
            f"Context Intelligence: {context_adj.get('mode', 'neutral')}",
            f"Context Pattern: {pattern_mode}",
            f"Narrativa de mercado: {meta_data.get('market_narrative', 'none')}",
            f"Qualidade de tendência: {meta_data.get('trend_quality', 'neutra')}",
            f"Qualidade de breakout: {meta_data.get('breakout_quality', 'ausente')}",
            f"Tipo de conflito: {meta_data.get('conflict_type', 'neutro')}",
            f"Estratégia líder: {leader_name}",
            f"Strategy score: {round(leader_score, 2)}",
            f"Evolução: {evolution_variant}",
            f"Capital Mind: {capital_plan.get('phase', 'neutral')}",
            f"Stake sugerida: {capital_plan.get('stake_value', 0.0)}",
            f"Score ajustado: {round(adjusted_score, 2)}",
            "Modo: v13 etapa 8 meta-context reasoning"
        ])

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": confidence,
            "regime": regime,
            "reasons": reasons,
            "setup_id": leader_setup_id,
            "context_id": leader_context_id,
            "strategy_name": leader_name,
            "evolution_variant": evolution_variant,
            "context_intelligence_mode": context_adj.get("mode", "neutral"),
            "context_pattern_mode": pattern_mode,
            "market_narrative": meta_data.get("market_narrative", "none"),
            "trend_quality": meta_data.get("trend_quality", "neutra"),
            "breakout_quality": meta_data.get("breakout_quality", "ausente"),
            "conflict_type": meta_data.get("conflict_type", "neutro"),
            "capital_phase": capital_plan.get("phase", "neutral"),
            "suggested_stake": capital_plan.get("stake_value", 0.0),
            "risk_pct": capital_plan.get("risk_pct", 0.0),
            "target_value": capital_plan.get("target_value", 0.0),
            "stop_value": capital_plan.get("stop_value", 0.0)
        }
