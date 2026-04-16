from __future__ import annotations

from typing import Any, Dict, List, Tuple

from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import CouncilDecision, MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.council.consensus_rules import classify_quality
from alpha_hive.council.conflict_rules import conflict_level
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine


class CouncilEngine:
    def __init__(self, reputation_engine: SpecialistReputationEngine | None = None):
        self.reputation = reputation_engine or SpecialistReputationEngine()

    def _context(self, features: MarketFeatures, consensus_quality: str) -> Dict[str, Any]:
        return {
            "trend_m1": features.trend_m1,
            "trend_m5": features.trend_m5,
            "multi_tf_conflict": str(features.trend_m1) != str(features.trend_m5),
            "breakout_quality": features.breakout_quality,
            "rejection_quality": features.rejection_quality,
            "explosive_expansion": bool(features.explosive_expansion),
            "late_entry_risk": bool(features.late_entry_risk),
            "is_sideways": bool(features.is_sideways),
            "trend_quality_signal": features.trend_quality_signal,
            "consensus_quality": consensus_quality,
        }

    def _rank_support(
        self,
        snapshot: MarketSnapshot,
        features: MarketFeatures,
        votes: List[SpecialistVote],
        consensus_quality: str,
        include_reasons: bool = False,
    ) -> Tuple[Dict[str, float], List[Tuple[float, str, str]], List[str]]:
        hour_bucket = f"{now_brazil().hour:02d}:00"
        support = {"CALL": 0.0, "PUT": 0.0}
        ranked: List[Tuple[float, str, str]] = []
        reasons: List[str] = []

        extra_context = self._context(features, consensus_quality)

        for vote in votes:
            if include_reasons and vote.veto:
                reasons.append(f"{vote.specialist} aplicou veto contextual")

            if vote.direction not in ("CALL", "PUT"):
                continue

            rep_weight = self.reputation.weight_for(
                specialist=vote.specialist,
                asset=snapshot.asset,
                direction=vote.direction,
                regime=features.regime,
                provider=snapshot.provider.split("-")[0],
                market_type=snapshot.market_type,
                hour_bucket=hour_bucket,
                setup_quality=vote.setup_quality,
                extra_context=extra_context,
            )

            fit_weight = max(0.72, min(1.12, 0.72 + float(vote.market_fit or 0.0) * 0.40))
            conviction_weight = max(0.82, min(1.08, 0.82 + (int(vote.confidence or 50) - 50) / 250.0))

            weighted = vote.vote_strength * rep_weight * fit_weight * conviction_weight

            if vote.setup_quality == "fragil":
                weighted *= 0.94
            elif vote.setup_quality == "premium":
                weighted *= 1.04

            if features.regime_transition_state in ("transition", "exhaustion") and vote.specialist in ("timing", "volatility", "regime"):
                weighted *= 1.06

            if bool(features.is_sideways) and vote.specialist in ("mean_reversion", "reversal", "regime"):
                weighted *= 1.08

            if features.trend_m1 == features.trend_m5 and vote.specialist in ("trend", "breakout", "timing"):
                weighted *= 1.06

            support[vote.direction] += weighted
            ranked.append((weighted, vote.specialist, vote.direction))

        return support, ranked, reasons

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures, votes: List[SpecialistVote]) -> CouncilDecision:
        support_first, _, _ = self._rank_support(snapshot, features, votes, "pre", include_reasons=False)
        total_first = support_first["CALL"] + support_first["PUT"]

        if total_first <= 0:
            return CouncilDecision(
                None,
                0.0,
                "split",
                0.0,
                0.0,
                "high",
                "OBSERVAR",
                [],
                ["Sem suporte suficiente"],
            )

        provisional_direction = "CALL" if support_first["CALL"] >= support_first["PUT"] else "PUT"
        provisional_support = support_first[provisional_direction]
        provisional_opposition = support_first["PUT" if provisional_direction == "CALL" else "CALL"]
        provisional_strength = round(provisional_support / max(total_first, 1e-9), 2)
        provisional_quality = classify_quality(provisional_strength, provisional_support, provisional_opposition)

        support, specialists_ranked, reasons = self._rank_support(
            snapshot,
            features,
            votes,
            provisional_quality,
            include_reasons=True,
        )

        total_weight = support["CALL"] + support["PUT"]
        if total_weight <= 0:
            return CouncilDecision(
                None,
                0.0,
                "split",
                0.0,
                0.0,
                "high",
                "OBSERVAR",
                [],
                reasons + ["Sem suporte suficiente"],
            )

        direction = "CALL" if support["CALL"] >= support["PUT"] else "PUT"
        support_weight = support[direction]
        opposition_weight = support["PUT" if direction == "CALL" else "CALL"]
        strength = round(support_weight / max(total_weight, 1e-9), 2)
        quality = classify_quality(strength, support_weight, opposition_weight)

        if features.regime_transition_state in ("transition", "exhaustion") and quality == "prime":
            quality = "measured"
            reasons.append("Transição/exaustão reduziu qualidade do consenso")

        destructive_conflict = strength < 0.52 and support_weight <= (opposition_weight * 1.03)
        decision_cap = None

        if quality == "split":
            decision_cap = "OBSERVAR" if destructive_conflict else "ENTRADA_CAUTELA"
            reasons.append("Split destrutivo: observação forçada" if destructive_conflict else "Split controlado: liberando cautela")
        elif quality == "fragile":
            decision_cap = "ENTRADA_CAUTELA"

        top_specialists = [
            name
            for _, name, side in sorted(specialists_ranked, reverse=True)
            if side == direction
        ][:3]

        reasons.append(f"Consenso {direction} com força {strength}")
        reasons.append(f"Qualidade contextual do conselho: {quality}")

        return CouncilDecision(
            consensus_direction=direction,
            consensus_strength=strength,
            quality=quality,
            support_weight=round(support_weight, 2),
            opposition_weight=round(opposition_weight, 2),
            conflict_level=conflict_level(strength),
            decision_cap=decision_cap,
            top_specialists=top_specialists,
            reasons=reasons[:12],
        )
