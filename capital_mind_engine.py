from __future__ import annotations

from typing import Dict

from alpha_hive.config import SETTINGS

class CapitalMindEngine:
    def get_plan(self, capital_state: Dict[str, float], base_confidence: int, setup_quality: str) -> Dict[str, float | str]:
        capital_current = float(capital_state.get("capital_current", 0.0) or 0.0)
        daily_pnl = float(capital_state.get("daily_pnl", 0.0) or 0.0)
        daily_target_pct = float(capital_state.get("daily_target_pct", 2.0) or 2.0)
        daily_stop_pct = float(capital_state.get("daily_stop_pct", 3.0) or 3.0)
        risk_pct = SETTINGS.default_risk_pct
        phase = "neutral"
        if capital_current > 0:
            if daily_pnl <= -(capital_current * daily_stop_pct / 100.0):
                risk_pct *= 0.2
                phase = "defensive"
            elif daily_pnl >= (capital_current * daily_target_pct / 100.0):
                risk_pct *= 0.5
                phase = "protected_gain"
            elif setup_quality == "premium" and base_confidence >= 80:
                risk_pct *= 1.15
                phase = "offense"
        stake_value = round(max(0.0, capital_current * risk_pct), 2)
        return {"phase": phase, "risk_pct": round(risk_pct, 4), "stake_value": stake_value}
