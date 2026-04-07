from __future__ import annotations

def conflict_level(consensus_strength: float) -> str:
    if consensus_strength >= 0.78:
        return "low"
    if consensus_strength >= 0.60:
        return "medium"
    return "high"
