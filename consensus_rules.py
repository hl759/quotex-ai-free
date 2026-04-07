from __future__ import annotations

def classify_quality(consensus_strength: float, support_weight: float, opposition_weight: float) -> str:
    if consensus_strength >= 0.80 and support_weight >= 2.5 * max(opposition_weight, 0.1):
        return "prime"
    if consensus_strength >= 0.66 and support_weight >= 1.6 * max(opposition_weight, 0.1):
        return "measured"
    if consensus_strength >= 0.54:
        return "fragile"
    return "split"
