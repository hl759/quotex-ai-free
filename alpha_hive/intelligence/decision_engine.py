from __future__ import annotations

from typing import List

from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import FinalDecision, MarketSnapshot, SpecialistVote
from alpha_hive.core.enums import DecisionLabel
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

    def decide(self, snapshot: MarketSnapshot, capital_state: dict | None = None) -> FinalDecision:
        capital_state = capital_state or {}
        features, votes = self._votes(snapshot)
        setup_quality = self._setup_quality(votes)
        council = self.council.evaluate(snapshot, features, votes)

        base_score = sum(v.vote_strength for v in votes if not v.veto)
        calibration = self.learning.calibration_profile(snapshot.asset)
        score = round(base_score + self.learning.asset_boost(snapshot.asset), 2)
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
            )
            score = round(score + float(segment_adj["score_boost"]), 2)
        confidence = int(max(50, min(95, (50 + score * 8) * calibration["confidence_factor"])))
        audit_summary = self.audit.compute_report()
        risk = self.edge_guard.evaluate(snapshot, features, council, audit_summary, setup_quality)
        capital_plan = self.capital_mind.get_plan(capital_state, confidence, setup_quality)
        suggested_stake = round(float(capital_plan["stake_value"]) * risk.stake_multiplier, 2)
        risk_pct = round(float(capital_plan["risk_pct"]) * risk.stake_multiplier, 4)

        strong_exception = (
            council.consensus_direction in ("CALL", "PUT")
            and score >= 4.5
            and confidence >= 88
            and setup_quality in ("favoravel", "premium")
            and snapshot.data_quality_score >= 0.80
            and council.support_weight > council.opposition_weight
            and council.consensus_strength >= 0.50
            and not risk.hard_block
            and not risk.kill_switch
        )

        decision = DecisionLabel.NO_TRADE.value
        direction = None
        if not risk.hard_block and council.consensus_direction:
            direction = council.consensus_direction
            if risk.decision_cap == DecisionLabel.OBSERVE.value:
                decision = DecisionLabel.ENTRY_CAUTION.value if strong_exception else DecisionLabel.OBSERVE.value
            elif risk.decision_cap == DecisionLabel.ENTRY_CAUTION.value:
                decision = DecisionLabel.ENTRY_CAUTION.value
            else:
                min_score = float(calibration["min_score"])
                if council.quality in ("prime", "measured") and score >= min_score and setup_quality in ("premium", "favoravel"):
                    decision = DecisionLabel.ENTRY_STRONG.value if council.quality == "prime" and risk.execution_permission == "LIBERADO" else DecisionLabel.ENTRY_CAUTION.value
                elif score >= max(2.0, min_score - 0.4):
                    decision = DecisionLabel.OBSERVE.value
                else:
                    decision = DecisionLabel.NO_TRADE.value
        if features.regime == "sideways":
            if decision == DecisionLabel.ENTRY_STRONG.value:
                decision = DecisionLabel.ENTRY_CAUTION.value
            suggested_stake = round(min(suggested_stake, float(capital_plan["stake_value"]) * 0.35), 2)
            risk_pct = round(min(risk_pct, float(capital_plan["risk_pct"]) * 0.35), 4)

        danger_context = (
            risk.hard_block
            or snapshot.data_quality_score < 0.65
            or (council.conflict_level == "high" and council.consensus_strength < 0.50)
            or features.regime == "chaotic"
        )

        state = risk.state if decision != DecisionLabel.NO_TRADE.value else "DEFENSE" if danger_context else "OBSERVE"
        if features.regime == "sideways" and state == "OFFENSE":
            state = "CAUTION"
        reasons = []
        for vote in votes:
            reasons.extend([f"{vote.specialist}: {reason}" for reason in vote.reasons[:2]])
        reasons.extend(council.reasons)
        reasons.extend(risk.reasons)

        return FinalDecision(
            asset=snapshot.asset,
            state=state,
            decision=decision,
            direction=direction,
            confidence=confidence,
            score=score,
            setup_quality=setup_quality,
            consensus_quality=council.quality,
            execution_permission=risk.execution_permission,
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
