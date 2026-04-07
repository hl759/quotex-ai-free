from __future__ import annotations

from alpha_hive.core.contracts import CouncilDecision, FinalDecision, MarketFeatures

class NarrativeEngine:
    def summarize(self, decision: FinalDecision, features: MarketFeatures, council: CouncilDecision) -> list[str]:
        lines = [
            f"Regime: {features.regime}",
            f"Consenso: {council.consensus_direction or 'sem direção'} com força {council.consensus_strength}",
            f"Qualidade do consenso: {council.quality}",
            f"Setup: {decision.setup_quality}",
        ]
        return lines
