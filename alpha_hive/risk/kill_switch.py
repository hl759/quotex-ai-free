from __future__ import annotations

from typing import Dict

def evaluate_kill_switch(recent_summary: Dict[str, float]) -> bool:
    total = int(recent_summary.get("total", 0) or 0)
    expectancy_r = float(recent_summary.get("expectancy_r", 0.0) or 0.0)
    profit_factor = float(recent_summary.get("profit_factor", 0.0) or 0.0)
    if total >= 12 and expectancy_r <= -0.20 and profit_factor < 0.85:
        return True
    return False
