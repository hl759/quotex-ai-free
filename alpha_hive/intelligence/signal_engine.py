from __future__ import annotations

from alpha_hive.core.contracts import FinalDecision


class SignalEngine:
    def _confidence_label(self, confidence: int) -> str:
        if confidence >= 82:
            return "FORTE"
        if confidence >= 70:
            return "MÉDIO"
        return "CAUTELOSO"

    def to_payload(self, decision: FinalDecision) -> dict:
        features = dict(decision.features or {})
        regime = str(features.get("regime", "unknown"))
        trend_m1 = str(features.get("trend_m1", "unknown"))
        trend_m5 = str(features.get("trend_m5", "unknown"))
        confidence = int(decision.confidence or 50)
        reasons = list(decision.reasons or [])

        return {
            "asset": decision.asset,
            "signal": decision.direction,
            "decision": decision.decision,
            "state": decision.state,
            "confidence": confidence,
            "confidence_label": self._confidence_label(confidence),
            "score": decision.score,
            "setup_quality": decision.setup_quality,
            "consensus_quality": decision.consensus_quality,
            "execution_permission": decision.execution_permission,
            "suggested_stake": decision.suggested_stake,
            "stake_suggested": decision.suggested_stake,
            "risk_pct": decision.risk_pct,
            "provider": decision.provider,
            "market_type": decision.market_type,
            "regime": regime,
            "timeframe": "M1",
            "trend_m1": trend_m1,
            "trend_m5": trend_m5,
            "reasons": reasons,
        }
