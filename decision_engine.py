from config import DEFAULT_PAYOUT, MIN_PROVIDER_TRUST_TO_TRADE
from strategy_engine import StrategyEngine

try:
    from edge_guard import EdgeGuardEngine
except Exception:
    class EdgeGuardEngine:
        def evaluate(self, *args, **kwargs):
            return {
                "active": False,
                "mode": "live",
                "decision_cap": None,
                "stake_multiplier": 1.0,
                "live_allowed": True,
                "reasons": ["Edge Guard neutro"],
                "report": {},
            }

try:
    from trader_council_engine import TraderCouncilEngine
except Exception:
    class TraderCouncilEngine:
        def evaluate(self, *args, **kwargs):
            return {
                "active": False,
                "quality": "neutro",
                "consensus_direction": None,
                "score_boost": 0.0,
                "confidence_shift": 0,
                "decision_cap": None,
                "direction_override": None,
                "head_trader_action": "none",
                "reasons": ["Trader Council neutro"],
                "participants": [],
                "memory": {"summary": {"total": 0, "wins": 0, "losses": 0, "winrate": 0.0, "expectancy_r": 0.0, "avg_payout": 0.8, "breakeven_winrate": 55.56}, "scar_tissue": ["Sem memória"]},
                "summary": {},
            }

try:
    from strategy_variants_engine import StrategyVariantsEngine
except Exception:
    StrategyVariantsEngine = None

try:
    from strategy_lab import StrategyLab
except Exception:
    class StrategyLab:
        def register_setup(self, *args, **kwargs):
            return None
        def get_setup_boost(self, *args, **kwargs):
            return (0.0, "Strategy Lab neutro")

try:
    from adaptive_engine import AdaptiveEngine
except Exception:
    class AdaptiveEngine:
        def get_weight(self, *args, **kwargs):
            return 1.0
        def get_reason(self, *args, **kwargs):
            return "Peso adaptativo neutro"
        def should_soft_block(self, *args, **kwargs):
            return False

try:
    from memory_engine import MemoryEngine
except Exception:
    class MemoryEngine:
        def register_context(self, *args, **kwargs):
            return None
        def get_memory_boost(self, *args, **kwargs):
            return (0.0, "Memória neutra")
        def register_result(self, *args, **kwargs):
            return None

try:
    from market_profile_engine import MarketProfileEngine
except Exception:
    class MarketProfileEngine:
        def get_profile(self, *args, **kwargs):
            return {
                "mode": "neutral",
                "score_shift": 0.0,
                "consensus_bonus": 0.0,
                "confidence_shift": 0,
                "reason": "Mercado em equilíbrio"
            }
        def register_result(self, *args, **kwargs):
            return None

try:
    from strategy_evolution_engine import StrategyEvolutionEngine
except Exception:
    class StrategyEvolutionEngine:
        def get_adjustment(self, *args, **kwargs):
            return {"boost": 0.0, "reason": "Evolução neutra", "variant": "base"}

try:
    from capital_mind_engine import CapitalMindEngine
except Exception:
    class CapitalMindEngine:
        def get_plan(self, *args, **kwargs):
            return {
                "phase": "neutral",
                "risk_pct": 0.0,
                "stake_value": 0.0,
                "score_shift": 0.0,
                "confidence_shift": 0,
                "reason": "Capital Mind neutro",
                "target_value": 0.0,
                "stop_value": 0.0
            }

try:
    from context_intelligence_engine import ContextIntelligenceEngine
except Exception:
    class ContextIntelligenceEngine:
        def get_adjustment(self, *args, **kwargs):
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "reason": "Contexto neutro",
                "mode": "neutral"
            }

try:
    from context_pattern_intelligence_engine import ContextPatternIntelligenceEngine
except Exception:
    class ContextPatternIntelligenceEngine:
        def get_adjustment(self, *args, **kwargs):
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "reason": "Context Pattern neutro",
                "mode": "neutral"
            }

try:
    from meta_context_reasoning_engine import MetaContextReasoningEngine
except Exception:
    class MetaContextReasoningEngine:
        def get_adjustment(self, *args, **kwargs):
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "reasons": ["Meta-contexto neutro"],
                "meta_context": {
                    "market_narrative": "none",
                    "trend_quality": "neutra",
                    "breakout_quality": "ausente",
                    "conflict_type": "neutro"
                }
            }

try:
    from veteran_discernment_layer import VeteranDiscernmentLayer
except Exception:
    class VeteranDiscernmentLayer:
        def evaluate(self, *args, **kwargs):
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "quality": "aceitavel",
                "veto": False,
                "anti_pattern_risk": "unknown",
                "anti_pattern_sample": 0,
                "anti_pattern_winrate": 0.0,
                "reasons": ["Discernimento veterano neutro"]
            }

try:
    from environment_transition_engine import EnvironmentTransitionEngine
except Exception:
    class EnvironmentTransitionEngine:
        def analyze_transition(self, *args, **kwargs):
            return {
                "transition_probability": "low",
                "next_environment": "unknown",
                "reason": ["Sem transição relevante"]
            }

try:
    from risk_dominance_engine import RiskDominanceEngine
except Exception:
    class RiskDominanceEngine:
        def evaluate(self, *args, **kwargs):
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "veto": False,
                "downgrade": None,
                "reasons": ["Risk dominance neutro"]
            }

try:
    from adaptive_behavioral_orchestration_engine import AdaptiveBehavioralOrchestrationEngine
except Exception:
    class AdaptiveBehavioralOrchestrationEngine:
        def evaluate(
            self,
            asset,
            regime,
            analysis_time,
            environment_type,
            discernment_quality,
            anti_pattern_risk,
            transition_probability,
            next_environment,
            risk_veto,
            risk_downgrade,
            meta_context,
            current_score,
            current_confidence,
        ):
            reasons = []
            score_boost = 0.0
            confidence_shift = 0
            frequency_limit = 1
            aggressiveness = "normal"
            acceptance_floor = "aceitavel"
            downgrade = None
            veto = False

            narrative = str(meta_context.get("market_narrative", "none"))
            conflict_type = str(meta_context.get("conflict_type", "neutro"))
            breakout_quality = str(meta_context.get("breakout_quality", "ausente"))

            if risk_veto or environment_type == "destructive":
                behavior_mode = "SURVIVAL"
            elif environment_type == "clean" and discernment_quality in ("premium", "bom"):
                behavior_mode = "EXPANSION"
            elif environment_type in ("complex", "structured_chaos") or transition_probability in ("medium", "high"):
                behavior_mode = "CAUTIOUS"
            else:
                behavior_mode = "BALANCED"

            if behavior_mode == "EXPANSION":
                score_boost += 0.08
                confidence_shift += 2
                frequency_limit = 2
                aggressiveness = "elevated"
                acceptance_floor = "aceitavel"
                reasons.append("Modo comportamental: EXPANSION")
            elif behavior_mode == "BALANCED":
                reasons.append("Modo comportamental: BALANCED")
            elif behavior_mode == "CAUTIOUS":
                score_boost -= 0.08
                confidence_shift -= 2
                aggressiveness = "reduced"
                acceptance_floor = "bom"
                reasons.append("Modo comportamental: CAUTIOUS")
                if current_score + score_boost < 3.0 or discernment_quality == "aceitavel":
                    downgrade = "OBSERVAR"
                    reasons.append("Orquestração: cautela rebaixa contexto marginal")
            else:
                score_boost -= 0.18
                confidence_shift -= 5
                frequency_limit = 0
                aggressiveness = "minimal"
                acceptance_floor = "premium"
                reasons.append("Modo comportamental: SURVIVAL")
                if (current_score + score_boost) < 3.8 or discernment_quality != "premium":
                    veto = True
                    reasons.append("Orquestração final: sobrevivência vetou a entrada")
                else:
                    downgrade = "OBSERVAR"
                    reasons.append("Orquestração final: sobrevivência só permite observação")

            if conflict_type == "destrutivo" and breakout_quality == "armadilha":
                veto = True
                reasons.append("Orquestração: conflito destrutivo + armadilha forçam veto")

            if narrative in ("distribuicao", "exaustao") and transition_probability == "high":
                veto = True
                reasons.append("Orquestração: narrativa tóxica com transição alta")

            if risk_downgrade == "OBSERVAR" and downgrade != "OBSERVAR":
                downgrade = "OBSERVAR"
                reasons.append("Orquestração: respeitando downgrade do risk dominance")
            elif risk_downgrade == "CAUTELA" and downgrade is None and behavior_mode in ("EXPANSION", "BALANCED"):
                downgrade = "CAUTELA"
                reasons.append("Orquestração: respeitando cautela do risk dominance")

            return {
                "behavior_mode": behavior_mode,
                "score_boost": round(score_boost, 2),
                "confidence_shift": int(confidence_shift),
                "frequency_limit": int(frequency_limit),
                "aggressiveness": aggressiveness,
                "acceptance_floor": acceptance_floor,
                "downgrade": downgrade,
                "veto": veto,
                "memory_sample": 0,
                "memory_winrate": 0.0,
                "reasons": reasons,
            }


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
        self.veteran_discernment = VeteranDiscernmentLayer()
        self.transition_engine = EnvironmentTransitionEngine()
        self.risk_dominance_engine = RiskDominanceEngine()
        self.behavioral_orchestration_engine = AdaptiveBehavioralOrchestrationEngine()
        self.edge_guard_engine = EdgeGuardEngine()
        self.trader_council_engine = TraderCouncilEngine()

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
            score -= 0.80
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

        if text.startswith("trend"):
            family = "trend"
        elif text.startswith("reversal"):
            family = "reversal"
        elif text.startswith("scalp"):
            family = "scalp"
        else:
            family = "other"

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

    def _classify_environment(self, meta):
        trend = meta.get("trend_quality")
        breakout = meta.get("breakout_quality")
        conflict = meta.get("conflict_type")
        narrative = meta.get("market_narrative")

        if trend == "forte" and breakout == "limpo" and conflict == "util":
            return "clean"

        if narrative in ("compressao_pre_breakout", "transicao"):
            return "complex"

        if narrative in ("expansao", "acumulacao") and conflict != "destrutivo":
            return "structured_chaos"

        if narrative in ("exaustao", "distribuicao") or breakout == "armadilha" or conflict == "destrutivo":
            return "destructive"

        return "complex"

    def _quality_rank(self, text):
        order = {
            "premium": 4,
            "bom": 3,
            "aceitavel": 2,
            "duvidoso": 1,
            "vetado": 0,
        }
        return order.get(str(text), 0)

    def _apply_edge_guard(self, decision, guard, final_direction, reasons):
        cap = guard.get("decision_cap")
        if not cap:
            return decision, final_direction
        if cap == "NAO_OPERAR":
            if decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA") and float(guard.get("stake_multiplier", 0.0) or 0.0) >= 0.18:
                reasons.append("Edge Guard final: bloqueio convertido em cautela por edge funcional")
                return "ENTRADA_CAUTELA", final_direction
            reasons.append("Edge Guard final: bloqueio total")
            return "NAO_OPERAR", None
        if cap == "OBSERVAR" and decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
            if (
                decision == "ENTRADA_CAUTELA"
                and bool(guard.get("live_allowed", True))
                and float(guard.get("stake_multiplier", 0.0) or 0.0) >= 0.32
            ):
                reasons.append("Edge Guard final: observação convertida em cautela reduzida")
                return "ENTRADA_CAUTELA", final_direction
            reasons.append("Edge Guard final: entrada rebaixada para observação")
            return "OBSERVAR", final_direction
        if cap == "ENTRADA_CAUTELA" and decision == "ENTRADA_FORTE":
            reasons.append("Edge Guard final: entrada forte rebaixada para cautela")
            return "ENTRADA_CAUTELA", final_direction
        return decision, final_direction


    def _apply_council_cap(self, decision, council, final_direction, reasons):
        cap = council.get("decision_cap")
        if not cap:
            return decision, final_direction
        if cap == "NAO_OPERAR":
            if decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA") and council.get("quality") in ("measured", "prime") and float(council.get("support_weight", 0.0) or 0.0) > 0:
                reasons.append("Trader Council final: bloqueio convertido em cautela operável")
                return "ENTRADA_CAUTELA", final_direction
            reasons.append("Trader Council final: bloqueio da mesa veterana")
            return "NAO_OPERAR", None
        if cap == "OBSERVAR" and decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
            if (
                decision == "ENTRADA_CAUTELA"
                and council.get("quality") in ("measured", "prime")
                and council.get("head_trader_action") in ("probe", "observe", "press")
                and float(council.get("support_weight", 0.0) or 0.0) >= max(2.8, float(council.get("opposition_weight", 0.0) or 0.0) * 1.02)
            ):
                reasons.append("Trader Council final: mesa preservou cautela operável")
                return "ENTRADA_CAUTELA", final_direction
            reasons.append("Trader Council final: mesa rebaixou entrada para observação")
            return "OBSERVAR", final_direction
        if cap == "ENTRADA_CAUTELA" and decision == "ENTRADA_FORTE":
            reasons.append("Trader Council final: mesa rebaixou entrada forte para cautela")
            return "ENTRADA_CAUTELA", final_direction
        return decision, final_direction

    def _apply_stake_multiplier(self, capital_plan, multiplier):
        mult = max(0.0, min(1.0, float(multiplier or 1.0)))
        out = dict(capital_plan or {})
        out["stake_value"] = round(float(out.get("stake_value", 0.0) or 0.0) * mult, 2)
        out["risk_pct"] = round(float(out.get("risk_pct", 0.0) or 0.0) * mult, 4)
        return out

    def decide(self, asset, indicators):
        regime = indicators.get("regime", "unknown")
        fallback_direction = indicators.get("direction", "CALL")
        analysis_time = indicators.get("analysis_time")
        weekday = indicators.get("weekday")

        market_profile = self.market_profile_engine.get_profile(regime)
        context_adj = self.context_intelligence_engine.get_adjustment(
            asset=asset,
            regime=regime,
            analysis_time=analysis_time,
            weekday=weekday,
        )

        base_score, base_reasons = self._build_base_score(indicators)
        reasons = [f"Score base: {base_score}"] + base_reasons + [
            market_profile.get("reason", "Mercado em equilíbrio"),
            context_adj.get("reason", "Contexto neutro"),
        ]

        base_candidates = [
            s for s in self.strategy_engine.evaluate_all(asset, indicators)
            if s.get("valid")
        ]
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
        meta_data = {
            "market_narrative": "none",
            "trend_quality": "neutra",
            "breakout_quality": "ausente",
            "conflict_type": "neutro",
        }
        discernment_quality = "aceitavel"
        discernment_veto = False
        anti_pattern_risk = "unknown"

        if candidates:
            fusion_total = 0.0
            used = []

            for s in candidates[:4]:
                strategy_name = s.get("strategy", "none")

                if self.adaptive_engine.should_soft_block(strategy_name, regime):
                    filtered.append(strategy_name)
                    reasons.append(f"Estratégia temporariamente enfraquecida: {strategy_name}")
                    continue

                pattern_adj = self.context_pattern_engine.get_adjustment(
                    asset=asset,
                    regime=regime,
                    strategy_name=strategy_name,
                    analysis_time=analysis_time,
                )
                final_weight = (
                    self._weight_by_regime(strategy_name, regime)
                    * self.adaptive_engine.get_weight(strategy_name, regime)
                )
                fusion_total += (
                    float(s.get("score", 0.0)) + pattern_adj.get("score_boost", 0.0)
                ) * final_weight
                used.append(strategy_name)

            adjusted_score += fusion_total

            if len(used) > 1:
                reasons.append(f"Contextos em competição: {', '.join(used[:3])}")
            elif used:
                reasons.append(f"Estratégia líder: {used[0]}")
            else:
                reasons.append("Estratégias válidas sem força operacional suficiente")

            leader = next((c for c in candidates if c.get("strategy") not in filtered), candidates[0])
            leader_name = leader.get("strategy", "none")
            leader_score = float(leader.get("score", 0.0))
            reasons.extend(leader.get("reasons", []))
            reasons.append(f"Estratégias válidas: {len(candidates)}")

            pattern_adj = self.context_pattern_engine.get_adjustment(
                asset=asset,
                regime=regime,
                strategy_name=leader_name,
                analysis_time=analysis_time,
            )
            adjusted_score += pattern_adj.get("score_boost", 0.0)
            reasons.append(pattern_adj.get("reason", "Context Pattern neutro"))
            pattern_conf_shift = pattern_adj.get("confidence_shift", 0)
            pattern_mode = pattern_adj.get("mode", "neutral")

            meta_adj = self.meta_context_engine.get_adjustment(
                asset=asset,
                strategy_name=leader_name,
                indicators=indicators,
                analysis_time=analysis_time,
            )
            adjusted_score += meta_adj.get("score_boost", 0.0)
            meta_conf_shift = meta_adj.get("confidence_shift", 0)
            meta_data = meta_adj.get("meta_context", meta_data)
            reasons.extend(meta_adj.get("reasons", []))

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
        base_confidence += int(segment_adjustment.get("confidence_shift", 0) or 0)
        base_confidence += context_adj.get("confidence_shift", 0)
        base_confidence += pattern_conf_shift
        base_confidence += meta_conf_shift

        if consensus_bonus > 0:
            base_confidence += 2

        base_confidence = int(max(50, min(95, base_confidence)))

        discernment = self.veteran_discernment.evaluate(
            asset=asset,
            strategy_name=leader_name,
            indicators=indicators,
            current_score=adjusted_score,
            current_confidence=base_confidence,
            meta_context=meta_data,
        )
        adjusted_score += discernment.get("score_boost", 0.0)
        base_confidence += discernment.get("confidence_shift", 0)
        reasons.extend(discernment.get("reasons", []))
        discernment_quality = discernment.get("quality", "aceitavel")
        discernment_veto = discernment.get("veto", False)
        anti_pattern_risk = discernment.get("anti_pattern_risk", "unknown")

        environment = self._classify_environment(meta_data)
        reasons.append(f"Ambiente operacional: {environment}")

        transition = self.transition_engine.analyze_transition(meta_data)
        reasons.append(
            f"Transição: {transition.get('transition_probability', 'low')} → {transition.get('next_environment', 'unknown')}"
        )
        for r in transition.get("reason", []):
            reasons.append(r)

        risk_dom = self.risk_dominance_engine.evaluate(
            environment_type=environment,
            meta_context=meta_data,
            transition_data=transition,
            current_score=adjusted_score,
            current_confidence=base_confidence,
        )
        adjusted_score += risk_dom.get("score_boost", 0.0)
        base_confidence += risk_dom.get("confidence_shift", 0)
        reasons.extend(risk_dom.get("reasons", []))

        behavior = self.behavioral_orchestration_engine.evaluate(
            asset=asset,
            regime=regime,
            analysis_time=analysis_time,
            environment_type=environment,
            discernment_quality=discernment_quality,
            anti_pattern_risk=anti_pattern_risk,
            transition_probability=transition.get("transition_probability", "low"),
            next_environment=transition.get("next_environment", "unknown"),
            risk_veto=risk_dom.get("veto", False),
            risk_downgrade=risk_dom.get("downgrade"),
            meta_context=meta_data,
            current_score=adjusted_score,
            current_confidence=base_confidence,
        )
        adjusted_score += behavior.get("score_boost", 0.0)
        base_confidence += behavior.get("confidence_shift", 0)
        reasons.extend(behavior.get("reasons", []))

        council = self.trader_council_engine.evaluate(
            asset=asset,
            indicators={**indicators, "environment_type": environment},
            candidates=candidates,
            leader_name=leader_name,
            final_direction=final_direction,
            current_score=adjusted_score,
            current_confidence=base_confidence,
            meta_context=meta_data,
            environment_type=environment,
            discernment_quality=discernment_quality,
            anti_pattern_risk=anti_pattern_risk,
        )
        adjusted_score += council.get("score_boost", 0.0)
        base_confidence += council.get("confidence_shift", 0)
        reasons.extend(council.get("reasons", []))
        if council.get("direction_override"):
            final_direction = council.get("direction_override")
            reasons.append(f"Trader Council: direção priorizada {final_direction}")

        capital_plan = self.capital_mind_engine.get_plan(
            asset=asset,
            adjusted_score=adjusted_score,
            confidence=base_confidence,
            indicators=indicators,
        )
        adjusted_score += capital_plan.get("score_shift", 0.0)
        reasons.append(capital_plan.get("reason", "Capital Mind neutro"))

        if discernment_veto or risk_dom.get("veto", False) or behavior.get("veto", False):
            decision, direction = "NAO_OPERAR", None
        else:
            if environment == "destructive":
                decision, direction = "NAO_OPERAR", None
            elif environment == "clean":
                if adjusted_score >= 2.45:
                    decision, direction = "ENTRADA_FORTE", final_direction
                elif adjusted_score >= 1.40:
                    decision, direction = "ENTRADA_CAUTELA", final_direction
                else:
                    decision, direction = "OBSERVAR", final_direction
            elif environment == "complex":
                if adjusted_score >= 2.35 and discernment_quality in ("premium", "bom", "aceitavel"):
                    decision, direction = "ENTRADA_CAUTELA", final_direction
                elif adjusted_score >= 1.55 and discernment_quality in ("premium", "bom", "aceitavel"):
                    decision, direction = "OBSERVAR", final_direction
                else:
                    decision, direction = "NAO_OPERAR", None
            elif environment == "structured_chaos":
                if adjusted_score >= 2.55 and discernment_quality in ("premium", "bom", "aceitavel"):
                    decision, direction = "ENTRADA_CAUTELA", final_direction
                elif adjusted_score >= 1.85 and discernment_quality in ("premium", "bom", "aceitavel"):
                    decision, direction = "OBSERVAR", final_direction
                else:
                    decision, direction = "NAO_OPERAR", None
            else:
                decision, direction = "NAO_OPERAR", None

            if risk_dom.get("downgrade") == "CAUTELA" and decision == "ENTRADA_FORTE":
                decision = "ENTRADA_CAUTELA"
                reasons.append("Risk dominance final: entrada forte rebaixada para cautela")
            elif risk_dom.get("downgrade") == "OBSERVAR" and decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
                decision = "OBSERVAR"
                reasons.append("Risk dominance final: entrada rebaixada para observação")

            if behavior.get("downgrade") == "CAUTELA" and decision == "ENTRADA_FORTE":
                decision = "ENTRADA_CAUTELA"
                reasons.append("Orquestração final: entrada forte rebaixada para cautela")
            elif behavior.get("downgrade") == "OBSERVAR" and decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
                decision = "OBSERVAR"
                reasons.append("Orquestração final: entrada rebaixada para observação")

            decision, direction = self._apply_council_cap(decision, council, final_direction, reasons)

            floor_rank = self._quality_rank(behavior.get("acceptance_floor", "aceitavel"))
            current_rank = self._quality_rank(discernment_quality)
            if current_rank < floor_rank:
                decision, direction = "NAO_OPERAR", None
                reasons.append("Orquestração final: contexto abaixo do piso de aceitação")

            if behavior.get("frequency_limit", 1) == 0 and decision != "NAO_OPERAR":
                decision, direction = "OBSERVAR", final_direction
                reasons.append("Orquestração final: limite de frequência travou entrada")

            if decision in ("NAO_OPERAR", "OBSERVAR"):
                premium_or_good = discernment_quality in ("premium", "bom")
                no_hard_veto = not (discernment_veto or risk_dom.get("veto", False) or behavior.get("veto", False) or environment == "destructive")
                if (
                    premium_or_good
                    and no_hard_veto
                    and anti_pattern_risk not in ("high", "critical")
                    and adjusted_score >= 3.4
                    and (base_confidence + capital_plan.get("confidence_shift", 0)) >= 74
                    and meta_data.get("conflict_type", "neutro") in ("util", "transicional", "neutro")
                ):
                    decision, direction = "ENTRADA_CAUTELA", final_direction
                    reasons.append("Rebalance final: contexto bom/premium preservou cautela operável")

        confidence = base_confidence + capital_plan.get("confidence_shift", 0)
        confidence = int(max(50, min(95, confidence)))

        provider_trust_score = float(indicators.get("provider_trust_score", 1.0) or 1.0)
        provider_is_fallback = bool(indicators.get("provider_is_fallback", False))
        market_type = str(indicators.get("market_type", "unknown") or "unknown")

        if market_type == "crypto" and provider_is_fallback and provider_trust_score < MIN_PROVIDER_TRUST_TO_TRADE and decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
            decision, direction = "NAO_OPERAR", None
            reasons.append("Filtro operacional: feed alternativo fraco para cripto M1")

        edge_guard = self.edge_guard_engine.evaluate(
            asset=asset,
            regime=regime,
            strategy_name=leader_name,
            analysis_time=analysis_time,
            proposed_decision=decision,
            proposed_score=adjusted_score,
            proposed_confidence=confidence,
        )
        decision, direction = self._apply_edge_guard(decision, edge_guard, final_direction, reasons)
        capital_plan = self._apply_stake_multiplier(capital_plan, edge_guard.get("stake_multiplier", 1.0))
        for r in edge_guard.get("reasons", []):
            reasons.append(f"Edge Guard: {r}")

        reasons.extend([
            f"Regime final: {regime}",
            f"Trader Council quality: {council.get('quality', 'neutro')}",
            f"Trader Council consensus: {council.get('consensus_direction', 'none')}",
            f"Head Trader action: {council.get('head_trader_action', 'none')}",
            f"Perfil de mercado: {market_profile.get('mode', 'neutral')}",
            f"Context Intelligence: {context_adj.get('mode', 'neutral')}",
            f"Context Pattern: {pattern_mode}",
            f"Narrativa de mercado: {meta_data.get('market_narrative', 'none')}",
            f"Qualidade de tendência: {meta_data.get('trend_quality', 'neutra')}",
            f"Qualidade de breakout: {meta_data.get('breakout_quality', 'ausente')}",
            f"Tipo de conflito: {meta_data.get('conflict_type', 'neutro')}",
            f"Discernimento veterano: {discernment_quality}",
            f"Anti-pattern risk: {anti_pattern_risk}",
            f"Probabilidade de transição: {transition.get('transition_probability', 'low')}",
            f"Próximo ambiente provável: {transition.get('next_environment', 'unknown')}",
            f"Modo comportamental: {behavior.get('behavior_mode', 'BALANCED')}",
            f"Agressividade: {behavior.get('aggressiveness', 'normal')}",
            f"Piso de aceitação: {behavior.get('acceptance_floor', 'aceitavel')}",
            f"Memória comportamental: {behavior.get('memory_winrate', 0.0)}% em {behavior.get('memory_sample', 0)} casos",
            f"Estratégia líder: {leader_name}",
            f"Strategy score: {round(leader_score, 2)}",
            f"Evolução: {evolution_variant}",
            f"Capital Mind: {capital_plan.get('phase', 'neutral')}",
            f"Stake sugerida: {capital_plan.get('stake_value', 0.0)}",
            f"Score ajustado: {round(adjusted_score, 2)}",
            "Modo: v13 etapa 12 adaptive behavioral orchestration",
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
            "discernment_quality": discernment_quality,
            "anti_pattern_risk": anti_pattern_risk,
            "environment_type": environment,
            "transition_probability": transition.get("transition_probability", "low"),
            "next_environment": transition.get("next_environment", "unknown"),
            "behavior_mode": behavior.get("behavior_mode", "BALANCED"),
            "behavior_aggressiveness": behavior.get("aggressiveness", "normal"),
            "behavior_frequency_limit": behavior.get("frequency_limit", 1),
            "behavior_acceptance_floor": behavior.get("acceptance_floor", "aceitavel"),
            "capital_phase": capital_plan.get("phase", "neutral"),
            "suggested_stake": capital_plan.get("stake_value", 0.0),
            "risk_pct": capital_plan.get("risk_pct", 0.0),
            "target_value": capital_plan.get("target_value", 0.0),
            "stop_value": capital_plan.get("stop_value", 0.0),
            "trader_council": council,
            "council_quality": council.get("quality", "neutro"),
            "council_consensus_direction": council.get("consensus_direction"),
            "head_trader_action": council.get("head_trader_action", "none"),
            "council_participants": council.get("participants", []),
            "case_memory": council.get("memory", {}),
            "edge_guard_mode": edge_guard.get("mode", "validation"),
            "edge_guard_active": edge_guard.get("active", False),
            "edge_guard_live_allowed": edge_guard.get("live_allowed", True),
            "edge_guard_decision_cap": edge_guard.get("decision_cap"),
            "edge_guard_stake_multiplier": edge_guard.get("stake_multiplier", 1.0),
            "edge_guard_report": edge_guard.get("report", {}),
            "trend_m1": indicators.get("trend_m1", indicators.get("trend", "neutral")),
            "trend_m5": indicators.get("trend_m5", "neutral"),
            "breakout": indicators.get("breakout", False),
            "rejection": indicators.get("rejection", False),
            "volatility": indicators.get("volatility", False),
            "moved_too_fast": indicators.get("moved_too_fast", False),
            "explosive_expansion": indicators.get("explosive_expansion", False),
            "late_entry_risk": indicators.get("late_entry_risk", False),
            "extension_pct": indicators.get("extension_pct", 0.0),
            "is_sideways": indicators.get("is_sideways", False),
            "pattern": indicators.get("pattern"),
            "provider": indicators.get("provider", "auto"),
            "provider_trust_score": indicators.get("provider_trust_score", 1.0),
            "provider_is_fallback": indicators.get("provider_is_fallback", False),
            "market_type": indicators.get("market_type", "unknown"),
            "payout": float(indicators.get("payout", DEFAULT_PAYOUT) or DEFAULT_PAYOUT),
            "analysis_session": analysis_time,
        }
