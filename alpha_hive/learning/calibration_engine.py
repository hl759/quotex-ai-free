from __future__ import annotations

def confidence_factor(winrate_pct: float, total: int) -> float:
    if total < 20:
        return 1.0
    if winrate_pct >= 60:
        return 1.05
    if winrate_pct <= 43:
        return 0.93
    return 1.0
