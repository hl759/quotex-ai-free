import json
import os
from storage_paths import DATA_DIR, migrate_file
from json_safe import safe_dump
from state_store import get_state_store

from config import ADAPTIVE_MIN_TRADES, ADAPTIVE_STRONG_MIN_TRADES, ADAPTIVE_PROVEN_MIN_TRADES

os.makedirs(DATA_DIR, exist_ok=True)

STRATEGY_LAB_FILE = os.path.join(DATA_DIR, "alpha_hive_strategy_lab.json")
STORE_KEY = "strategy_lab_store"
migrate_file(STRATEGY_LAB_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_strategy_lab.json")])


class StrategyLab:
    def __init__(self):
        self.store = get_state_store()
        self.data = self._load()

    def _load(self):
        store_value = self.store.get_json(STORE_KEY, None)
        if isinstance(store_value, dict) and store_value:
            return store_value
        try:
            if os.path.exists(STRATEGY_LAB_FILE):
                with open(STRATEGY_LAB_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.store.set_json(STORE_KEY, data)
                        return data
        except Exception:
            pass
        return {}

    def _save(self):
        self.store.set_json(STORE_KEY, self.data)
        tmp = STRATEGY_LAB_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(self.data, f)
        os.replace(tmp, STRATEGY_LAB_FILE)

    def _hour_bucket(self, time_str):
        try:
            text = str(time_str).strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def build_setup_id(self, asset, strategy_name, indicators, analysis_time=None):
        regime = indicators.get("regime", "unknown")
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        breakout = "1" if indicators.get("breakout", False) else "0"
        rejection = "1" if indicators.get("rejection", False) else "0"
        pattern = indicators.get("pattern", "none")
        hour_bucket = self._hour_bucket(analysis_time)

        return "|".join([
            str(asset or "N/A"),
            str(strategy_name or "none"),
            str(regime),
            str(trend_m1),
            str(trend_m5),
            str(pattern),
            f"bo:{breakout}",
            f"rej:{rejection}",
            f"h:{hour_bucket}",
        ])

    def register_setup(self, asset, strategy_name, indicators, signal, analysis_time=None):
        setup_id = self.build_setup_id(asset, strategy_name, indicators, analysis_time)

        if setup_id not in self.data:
            self.data[setup_id] = {
                "setup_id": setup_id,
                "asset": asset,
                "strategy": strategy_name,
                "regime": indicators.get("regime", "unknown"),
                "hour": self._hour_bucket(analysis_time),
                "total": 0,
                "wins": 0,
                "loss": 0,
                "last_signal": signal,
            }
            self._save()

        return setup_id

    def register_result(self, setup_id, result):
        if not setup_id:
            return

        if setup_id not in self.data:
            return

        normalized = str(result).upper()
        if normalized not in ("WIN", "LOSS"):
            return

        self.data[setup_id]["total"] += 1
        if normalized == "WIN":
            self.data[setup_id]["wins"] += 1
        else:
            self.data[setup_id]["loss"] += 1

        self._save()

    def setup_stats(self, setup_id):
        info = self.data.get(setup_id)
        if not info:
            return {
                "setup_id": setup_id,
                "total": 0,
                "wins": 0,
                "loss": 0,
                "winrate": 0.0
            }

        total = int(info.get("total", 0))
        wins = int(info.get("wins", 0))
        loss = int(info.get("loss", 0))
        winrate = round((wins / total) * 100, 2) if total > 0 else 0.0

        return {
            **info,
            "winrate": winrate
        }

    def get_setup_boost(self, setup_id):
        stats = self.setup_stats(setup_id)
        total = stats.get("total", 0)
        winrate = stats.get("winrate", 0.0)

        if total < ADAPTIVE_MIN_TRADES:
            return 0.0, "Setup sem amostra suficiente"

        if total >= ADAPTIVE_PROVEN_MIN_TRADES:
            if winrate >= 70:
                return 0.28, "Setup comprovadamente forte"
            if winrate >= 62:
                return 0.12, "Setup consistente"
            if winrate <= 40:
                return -0.18, "Setup comprovadamente fraco"
        elif total >= ADAPTIVE_STRONG_MIN_TRADES:
            if winrate >= 67:
                return 0.18, "Setup forte"
            if winrate >= 60:
                return 0.08, "Setup favorável"
            if winrate <= 42:
                return -0.12, "Setup fraco"
        else:
            if winrate >= 64:
                return 0.08, "Setup promissor"
            if winrate <= 40:
                return -0.08, "Setup cauteloso"

        return 0.0, "Setup neutro"

    def top_setups(self, min_total=ADAPTIVE_MIN_TRADES, limit=10):
        rows = []
        for setup_id in self.data.keys():
            stats = self.setup_stats(setup_id)
            if stats.get("total", 0) >= min_total:
                rows.append(stats)

        rows.sort(key=lambda x: (x.get("winrate", 0.0), x.get("total", 0)), reverse=True)
        return rows[:limit]