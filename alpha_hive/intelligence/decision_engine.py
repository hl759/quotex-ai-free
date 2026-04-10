from __future__ import annotations

from typing import Any, Dict, List

from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import FinalDecision, MarketSnapshot, SpecialistVote
from alpha_hive.core.enums import DecisionLabel, ExecutionPermission
from alpha_hive.council.council_engine import CouncilEngine
from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.intelligence.feature_engine import FeatureEngine
from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.risk.capital_mind_engine import CapitalMindEngine
from alpha_hive.risk.edge_guard import EdgeGuard
from alpha_hive.specialists.breakout_specialist import BreakoutSpecialist
from alpha_hive.specialists.data_quality_specialist import DataQualitySpecialist
from alpha_hive.specialists.mean_reversion_specialist import MeanReversionSpecialist
from alpha_hive.specialists.regime_specialist import RegimeSpecialist
from alpha_hive.specialists.reversal_specialist import ReversalSpecialist
from alpha_hive.specialists.session_specialist import SessionSpecialist
from alpha_hive.specialists.timing_specialist import TimingSpecialist
from alpha_hive.specialists.trend_specialist import TrendSpecialist
from alpha_hive.specialists.volatility_specialist import VolatilitySpecialist


class DecisionEngine:
    def __init__(self):
        self.feature_engine = FeatureEngine()
        self.learning = LearningEngine()
        self.audit = EdgeAuditEngine()
        self.council = CouncilEngine()
        self.edge_guard = EdgeGuard()
        self.capital_mind = CapitalMindEngine()
        self.specialists = [
            TrendSpecialist(),
            ReversalSpecialist(),
            BreakoutSpecialist(),
            MeanReversionSpecialist(),
            VolatilitySpecialist(),
            RegimeSpecialist(),
            TimingSpecialist(),
            SessionSpecialist(),
            DataQualitySpecialist(),
        ]

    def _hour_bucket(self) -> str:
        return f"{now_brazil().hour:02d}:00"

    def _votes(self, snapshot: MarketSnapshot):
        features = self.feature_engine.extract(snapshot)
        votes = [specialist.evaluate(snapshot, features) for specialist in self.specialists]
        return features, votes

    def _setup_quality(self, votes: List[SpecialistVote]) -> str:
        ranking = {"fragil": 0, "monitorado": 1, "favoravel": 2, "premium": 3}
        best = "fragil"
        for vote in votes:
            if ranking.get(vote.setup_quality, 0) > ranking.get(best, 0):
                best = vote.setup_quality
        return best

    def _learning_context(self, features, council) -> Dict[str, Any]:
        return {
            "trend_m1": getattr(features, "trend_m1", "unknown"),
            "trend_m5": getattr(features, "trend_m5", "unknown"),
            "multi_tf_conflict": str(getattr(features, "trend_m1", "unknown")) != str(getattr(features, "trend_m5", "unknown")),
            "breakout_quality": getattr(features, "breakout_quality", "unknown"),
            "rejection_quality": getattr(features, "rejection_quality", "unknown"),
            "explosive_expansion": bool(getattr(features, "explosive_expansion", False)),
            "late_entry_risk": bool(getattr(features, "late_entry_risk", False)),
            "is_sideways": bool(getattr(features, "is_sideways", False)),
            "trend_quality_signal": getattr(features, "trend_quality_signal", "unknown"),
            "consensus_quality": getattr(council, "quality", "split"),
        }

    def decide(self, snapshot: MarketSnapshot, capital_state: dict | None = None) -> FinalDecision:
        capital_state = capital_state or {}
        features, votes = self._votes(snapshot)
        setup_quality = self._setup_quality(votes)
        council = self.council.evaluate(snapshot, features, votes)
        learning_context = self._learning_context(features, council)

        base_score = sum(v.vote_strength for v in votes if not v.veto)
        calibration = self.learning.calibration_profile(snapshot.asset)
        score = round(base_score + self.learning.asset_boost(snapshot.asset), 2)

        segment_adj = {
            "score_boost": 0.0,
            "confidence_shift": 0,
            "proof_state": "building",
            "trades": 0,
            "winrate": 0.0,
            "reverse_bias": 0.0,
            "cause_pressure": 0.0,
            "cooldown_state": "none",
            "loss_cause_leader": "none",
        }

        if council.consensus_direction:
            lead_specialist = council.top_specialists[0] if council.top_specialists else "trend"
            segment_adj = self.learning.segment_adjustment(
                asset=snapshot.asset,
                direction=council.consensus_direction,
                regime=features.regime,
                specialist=lead_specialist,
                provider=snapshot.provider.split("-")[0],
                market_type=snapshot.market_type,
                hour_bucket=self._hour_bucket(),
                setup_quality=setup_quality,
                extra_context=learning_context,
            )
            score = round(
                score
                + float(segment_adj.get("score_boost", 0.0) or 0.0)
                + float(segment_adj.get("reverse_bias", 0.0) or 0.0)
                - float(segment_adj.get("cause_pressure", 0.0) or 0.0),
                2,
            )

        proof_state = str(segment_adj.get("proof_state", "building"))
        segment_conf_shift = int(segment_adj.get("confidence_shift", 0) or 0)
        segment_trades = float(segment_adj.get("trades", 0) or 0)
        segment_winrate = float(segment_adj.get("winrate", 0.0) or 0.0)
        reverse_bias = float(segment_adj.get("reverse_bias", 0.0) or 0.0)
        cause_pressure = float(segment_adj.get("cause_pressure", 0.0) or 0.0)
        cooldown_state = str(segment_adj.get("cooldown_state", "none"))
        loss_cause_leader = str(segment_adj.get("loss_cause_leader", "none"))

        confidence = int(
            max(
                50,
                min(
                    95,
                    round(((50 + score * 8) * calibration["confidence_factor"]) + segment_conf_shift - (cause_pressure * 18)),
                ),
            )
        )

        audit_summary = self.audit.compute_report()
        risk = self.edge_guard.evaluate(snapshot, features, council, audit_summary, setup_quality)
        capital_plan = self.capital_mind.get_plan(capital_state, confidence, setup_quality)
        suggested_stake = round(float(capital_plan["stake_value"]) * risk.stake_multiplier, 2)
        risk_pct = round(float(capital_plan["risk_pct"]) * risk.stake_multiplier, 4)

        provider_lower = str(snapshot.provider or "").lower()
        veto_names = {vote.specialist for vote in votes if vote.veto}
        hard_context_veto = any(name in veto_names for name in ("volatility", "data_quality"))
        soft_context_veto = any(name in veto_names for name in ("timing",))

        stretched_context = bool(features.moved_too_fast or features.late_entry_risk or features.explosive_expansion)
        multi_tf_conflict = str(features.trend_m1) != str(features.trend_m5)
        breakout_chase = bool(features.breakout and str(features.breakout_quality) == "strong" and (stretched_context or multi_tf_conflict))
        sideways_context = bool(features.regime == "sideways" or features.is_sideways)

        positive_proof = proof_state == "proven_positive"
        negative_proof = proof_state == "proven_negative"

        regular_exception = (
            council.consensus_direction in ("CALL", "PUT")
            and council.quality in ("measured", "prime")
            and score >= (4.55 if positive_proof else 4.8)
            and confidence >= (86 if positive_proof else 89)
            and setup_quality in ("favoravel", "premium")
            and snapshot.data_quality_score >= SETTINGS.data_quality_min_operable
            and council.support_weight > council.opposition_weight
            and council.consensus_strength >= (0.56 if positive_proof else 0.58)
            and not risk.kill_switch
            and not risk.hard_block
            and features.regime != "chaotic"
            and not hard_context_veto
            and not soft_context_veto
            and not stretched_context
            and not breakout_chase
            and not negative_proof
            and cooldown_state != "hard"
            and reverse_bias > -0.18
        )

        cache_exception = (
            "-cache" in provider_lower
            and council.consensus_direction in ("CALL", "PUT")
            and council.quality in ("measured", "prime")
            and snapshot.data_quality_score >= 0.55
            and score >= (5.10 if positive_proof else 5.40)
            and confidence >= (88 if positive_proof else 91)
            and setup_quality == "premium"
            and council.support_weight > council.opposition_weight
            and council.consensus_strength >= (0.63 if positive_proof else 0.66)
            and not risk.kill_switch
            and not risk.hard_block
            and features.regime != "chaotic"
            and not hard_context_veto
            and not soft_context_veto
            and not stretched_context
            and not breakout_chase
            and not negative_proof
            and cooldown_state != "hard"
        )

        sideways_mean_reversion_exception = (
            "-cache" in provider_lower
            and sideways_context
            and council.consensus_direction in ("CALL", "PUT")
            and council.quality == "prime"
            and snapshot.data_quality_score >= 0.58
            and score >= (5.50 if positive_proof else 5.80)
            and confidence >= (90 if positive_proof else 92)
            and setup_quality == "premium"
            and bool(features.rejection)
            and multi_tf_conflict
            and not features.moved_too_fast
            and not features.late_entry_risk
            and not features.explosive_expansion
            and not risk.kill_switch
            and not risk.hard_block
            and not hard_context_veto
            and not soft_context_veto
            and not negative_proof
            and reverse_bias > -0.12
        )

        operable_exception = regular_exception or cache_exception or sideways_mean_reversion_exception

        decision = DecisionLabel.NO_TRADE.value
        direction = None

        if not risk.hard_block and council.consensus_direction:
            direction = council.consensus_direction
            min_score = float(calibration["min_score"])
            if positive_proof:
                min_score -= 0.18
            elif negative_proof:
                min_score += 0.28
            min_score += cause_pressure * 0.8
            if cooldown_state == "soft":
                min_score += 0.10

            if hard_context_veto:
                decision = DecisionLabel.OBSERVE.value
            elif breakout_chase or stretched_context:
                decision = DecisionLabel.OBSERVE.value
            elif cooldown_state == "hard" and council.quality != "prime":
                decision = DecisionLabel.OBSERVE.value
            elif reverse_bias <= -0.16 and council.quality != "prime":
                decision = DecisionLabel.OBSERVE.value
            elif negative_proof and council.quality != "prime":
                decision = DecisionLabel.OBSERVE.value
            elif sideways_context and council.quality == "fragile":
                decision = DecisionLabel.OBSERVE.value
            elif operable_exception:
                decision = DecisionLabel.ENTRY_CAUTION.value
            elif risk.decision_cap == DecisionLabel.OBSERVE.value:
                decision = DecisionLabel.OBSERVE.value
            elif risk.decision_cap == DecisionLabel.ENTRY_CAUTION.value:
                if (
                    council.quality in ("measured", "prime")
                    and setup_quality in ("favoravel", "premium")
                    and not multi_tf_conflict
                    and not negative_proof
                    and cooldown_state != "hard"
                ):
                    decision = DecisionLabel.ENTRY_CAUTION.value
                else:
                    decision = DecisionLabel.OBSERVE.value
            else:
                if (
                    council.quality == "prime"
                    and score >= (min_score + 0.35)
                    and setup_quality == "premium"
                    and features.regime == "trend"
                    and not multi_tf_conflict
                    and not hard_context_veto
                    and not stretched_context
                    and not breakout_chase
                    and not risk.kill_switch
                    and not negative_proof
                    and cooldown_state == "none"
                ):
                    decision = DecisionLabel.ENTRY_STRONG.value
                elif (
                    council.quality in ("measured", "prime")
                    and score >= min_score
                    and setup_quality in ("favoravel", "premium")
                    and not hard_context_veto
                    and not stretched_context
                    and not breakout_chase
                    and not negative_proof
                    and reverse_bias > -0.18
                ):
                    decision = DecisionLabel.ENTRY_CAUTION.value
                elif score >= max(2.0, min_score - 0.4):
                    decision = DecisionLabel.OBSERVE.value
                else:
                    decision = DecisionLabel.NO_TRADE.value

        if cooldown_state == "soft":
            suggested_stake = round(suggested_stake * 0.82, 2)
            risk_pct = round(risk_pct * 0.82, 4)
        elif cooldown_state == "hard":
            suggested_stake = round(suggested_stake * 0.55, 2)
            risk_pct = round(risk_pct * 0.55, 4)

        if sideways_context:
            if decision == DecisionLabel.ENTRY_STRONG.value:
                decision = DecisionLabel.ENTRY_CAUTION.value
            suggested_stake = round(min(suggested_stake, float(capital_plan["stake_value"]) * 0.35), 2)
            risk_pct = round(min(risk_pct, float(capital_plan["risk_pct"]) * 0.35), 4)

        danger_context = (
            risk.hard_block
            or snapshot.data_quality_score < SETTINGS.data_quality_min_operable
            or (council.conflict_level == "high" and council.consensus_strength < 0.50)
            or features.regime == "chaotic"
            or risk.kill_switch
        )

        if decision == DecisionLabel.ENTRY_STRONG.value:
            state = "OFFENSE"
        elif decision == DecisionLabel.ENTRY_CAUTION.value:
            state = "CAUTION"
        elif danger_context:
            state = "DEFENSE"
        else:
            state = "OBSERVE"

        if sideways_context and state == "OFFENSE":
            state = "CAUTION"
        if cooldown_state == "hard" and state == "OFFENSE":
            state = "CAUTION"

        if decision == DecisionLabel.ENTRY_STRONG.value:
            final_execution_permission = (
                ExecutionPermission.RELEASED.value
                if not sideways_context and "-cache" not in provider_lower and council.quality == "prime"
                else ExecutionPermission.CAUTION_OPERABLE.value
            )
        elif decision == DecisionLabel.ENTRY_CAUTION.value:
            final_execution_permission = ExecutionPermission.CAUTION_OPERABLE.value
        else:
            final_execution_permission = ExecutionPermission.BLOCKED.value

        reasons = []
        for vote in votes:
            reasons.extend([f"{vote.specialist}: {reason}" for reason in vote.reasons[:2]])
        reasons.extend(council.reasons)
        reasons.extend(risk.reasons)

        if hard_context_veto:
            reasons.append("Veto contextual sério impediu execução")
        if breakout_chase:
            reasons.append("Breakout esticado/conflitante rebaixado para observação")
        if stretched_context:
            reasons.append("Movimento já correu: execução tardia evitada")
        if positive_proof:
            reasons.append(f"Contexto aprendido positivamente ({segment_trades:.1f} trades, {segment_winrate:.2f}% winrate)")
        if negative_proof:
            reasons.append(f"Contexto aprendido negativamente ({segment_trades:.1f} trades, {segment_winrate:.2f}% winrate)")
        if reverse_bias <= -0.12:
            reasons.append("Memória contrafactual negativa: esse lado tem histórico recente de direção falha")
        if cause_pressure >= 0.10 and loss_cause_leader != "none":
            reasons.append(f"Pressão de falha recorrente: {loss_cause_leader}")
        if cooldown_state != "none":
            reasons.append(f"Cooldown contextual ativo: {cooldown_state}")
        if regular_exception:
            reasons.append("Exceção forte: setup liberado em cautela disciplinada")
        if cache_exception:
            reasons.append("Exceção de cache: operável apenas em cautela")
        if sideways_mean_reversion_exception:
            reasons.append("Exceção lateral com rejeição: operável apenas em cautela")

        return FinalDecision(
            asset=snapshot.asset,
            state=state,
            decision=decision,
            direction=direction,
            confidence=confidence,
            score=score,
            setup_quality=setup_quality,
            consensus_quality=council.quality,
            execution_permission=final_execution_permission,
            suggested_stake=suggested_stake,
            risk_pct=risk_pct,
            provider=snapshot.provider,
            market_type=snapshot.market_type,
            reasons=reasons[:30],
            specialist_votes=[vote.to_dict() for vote in votes],
            council=council.to_dict(),
            risk=risk.to_dict(),
            features=features.to_dict(),
        )
