from __future__ import annotations

from typing import Dict

from alpha_hive.storage.state_store import get_state_store

KEY = "capital_state_v2"

DEFAULT = {
    "capital_current": 0.0,
    "capital_peak": 0.0,
    "daily_pnl": 0.0,
    "streak": 0,
    "daily_target_pct": 2.0,
    "daily_stop_pct": 3.0,
}

class CapitalService:
    def __init__(self):
        self.store = get_state_store()

    def get(self) -> Dict[str, float]:
        data = self.store.get_json(KEY, DEFAULT.copy())
        if not isinstance(data, dict):
            return DEFAULT.copy()
        out = DEFAULT.copy()
        out.update(data)
        if float(out["capital_peak"]) < float(out["capital_current"]):
            out["capital_peak"] = float(out["capital_current"])
        return out

    def save(self, payload: Dict[str, float]) -> Dict[str, float]:
        current = self.get()
        current.update({k: payload.get(k, current[k]) for k in DEFAULT.keys()})
        if float(current["capital_peak"]) < float(current["capital_current"]):
            current["capital_peak"] = float(current["capital_current"])
        self.store.set_json(KEY, current)
        return current
