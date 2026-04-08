from __future__ import annotations

from typing import List

from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import CouncilDecision, MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.council.consensus_rules import classify_quality
from alpha_hive.council.conflict_rules import conflict_level
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine

class CouncilEngine:
    def __init__(self, reputation_engine: SpecialistReputationEngine | None = None):
        self.reputation = reputation_engine or SpecialistReputationEngine()

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures, votes: List[SpecialistVote]) -> CouncilDecision:
        hour_bucket = f"{now_brazil().hour:02d}:00"
        support = {"CALL": 0.0, "PUT": 0.0}
        specialists_ranked = []
        reasons = []
        decision_cap = None
        for vote in votes:
            if vote.veto:
                reasons.append(f"{vote.specialist} aplicou veto contextual")
            if vote.direction not in ("CALL", "PUT"):
                continue
            weight = self.reputation.weight_for(
                specialist=vote.specialist,
                asset=snapshot.asset,
                direction=vote.direction,
                regime=features.regime,
                provider=snapshot.provider.split("-")[0],
                market_type=snapshot.market_type,
                hour_bucket=hour_bucket,
                setup_quality=vote.setup_quality,
            )
            weighted = vote.vote_strength * weight
            support[vote.direction] += weighted
            specialists_ranked.append((weighted, vote.specialist, vote.direction))
        total_weight = support["CALL"] + support["PUT"]
        if total_weight <= 0:
            return CouncilDecision(None, 0.0, "split", 0.0, 0.0, "high", "OBSERVAR", [], reasons + ["Sem suporte suficiente"])
        direction = "CALL" if support["CALL"] >= support["PUT"] else "PUT"
        support_weight = support[direction]
        opposition_weight = support["PUT" if direction == "CALL" else "CALL"]
        strength = round(support_weight / max(total_weight, 1e-9), 2)
        quality = classify_quality(strength, support_weight, opposition_weight)
        if quality == "split":
            decision_cap = "OBSERVAR"
        elif quality == "fragile":
            decision_cap = "ENTRADA_CAUTELA"
        top_specialists = [name for _, name, side in sorted(specialists_ranked, reverse=True) if side == direction][:3]
        reasons.append(f"Consenso {direction} com força {strength}")
        return CouncilDecision(
            consensus_direction=direction,
            consensus_strength=strength,
            quality=quality,
            support_weight=round(support_weight, 2),
            opposition_weight=round(opposition_weight, 2),
            conflict_level=conflict_level(strength),
            decision_cap=decision_cap,
            top_specialists=top_specialists,
            reasons=reasons,
        )
