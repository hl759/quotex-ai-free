import json
import os
from json_safe import safe_dump, safe_dumps, to_jsonable

from config import ADAPTIVE_MIN_TRADES, ADAPTIVE_STRONG_MIN_TRADES

DATA_DIR = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
os.makedirs(DATA_DIR, exist_ok=True)

PROFILE_FILE = os.path.join(DATA_DIR, "alpha_hive_market_profile.json")


class MarketProfileEngine:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(PROFILE_FILE):
                with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {
            "global": {
                "mode": "neutral",
                "total": 0,
                "wins": 0,
                "loss": 0
            }
        }

    def _save(self):
        tmp = PROFILE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(self.data, f)
        os.replace(tmp, PROFILE_FILE)

    def register_result(self, regime, result):
        normalized = str(result).upper()
        if normalized not in ("WIN", "LOSS"):
            return

        self.data.setdefault("global", {"mode": "neutral", "total": 0, "wins": 0, "loss": 0})
        self.data["global"]["total"] += 1
        if normalized == "WIN":
            self.data["global"]["wins"] += 1
        else:
            self.data["global"]["loss"] += 1

        regime_key = str(regime or "unknown")
        self.data.setdefault(regime_key, {"mode": "neutral", "total": 0, "wins": 0, "loss": 0})
        self.data[regime_key]["total"] += 1
        if normalized == "WIN":
            self.data[regime_key]["wins"] += 1
        else:
            self.data[regime_key]["loss"] += 1

        for key in ("global", regime_key):
            row = self.data[key]
            total = int(row.get("total", 0))
            wins = int(row.get("wins", 0))
            if total < ADAPTIVE_MIN_TRADES:
                row["mode"] = "neutral"
                continue
            winrate = wins / total if total else 0.0
            if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate >= 0.62:
                row["mode"] = "aggressive"
            elif total >= ADAPTIVE_STRONG_MIN_TRADES and winrate <= 0.43:
                row["mode"] = "defensive"
            else:
                row["mode"] = "neutral"

        self._save()

    def _mode_for(self, regime):
        regime_key = str(regime or "unknown")
        row = self.data.get(regime_key)
        if row and int(row.get("total", 0)) >= ADAPTIVE_STRONG_MIN_TRADES:
            return row.get("mode", "neutral")
        global_row = self.data.get("global", {})
        if int(global_row.get("total", 0)) >= ADAPTIVE_STRONG_MIN_TRADES:
            return global_row.get("mode", "neutral")
        return "neutral"

    def get_profile(self, regime):
        mode = self._mode_for(regime)
        if mode == "aggressive":
            return {
                "mode": "aggressive",
                "score_shift": -0.06,
                "consensus_bonus": 0.04,
                "confidence_shift": 1,
                "reason": "Mercado favorece execução"
            }
        if mode == "defensive":
            return {
                "mode": "defensive",
                "score_shift": 0.10,
                "consensus_bonus": -0.02,
                "confidence_shift": -2,
                "reason": "Mercado pede defesa"
            }
        return {
            "mode": "neutral",
            "score_shift": 0.0,
            "consensus_bonus": 0.0,
            "confidence_shift": 0,
            "reason": "Mercado em equilíbrio"
        }