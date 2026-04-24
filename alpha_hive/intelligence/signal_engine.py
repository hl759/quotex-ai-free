from __future__ import annotations

from alpha_hive.core.contracts import FinalDecision


class SignalEngine:
    def to_payload(self, decision: FinalDecision) -> dict:
        features = dict(decision.features or {})
        return {
            "asset": decision.asset,
            "signal": decision.direction,
            "direction": decision.direction,
            "decision": decision.decision,
            "state": decision.state,
            "confidence": decision.confidence,
            "score": decision.score,
            "setup_quality": decision.setup_quality,
            "consensus_quality": decision.consensus_quality,
            "execution_permission": decision.execution_permission,
            "suggested_stake": decision.suggested_stake,
            "risk_pct": decision.risk_pct,
            "provider": decision.provider,
            "market_type": decision.market_type,
            "regime": features.get("regime", "unknown"),
            "features": features,
            "council": decision.council,
            "meta_rank_score": decision.meta_rank_score,
            "meta_state": decision.meta_state,
            "meta_reasons": decision.meta_reasons,
            "reasons": decision.reasons,
        }
