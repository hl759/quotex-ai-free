
import json
import os
from datetime import datetime

DATA_DIR = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
os.makedirs(DATA_DIR, exist_ok=True)

JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")
CAPITAL_STATE_FILE = os.path.join("/tmp/nexus_state", "capital_state.json")


class CapitalAutoTracker:
    def _load_json(self, path, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data
        except Exception:
            pass
        return default

    def _save_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def _default_capital_state(self):
        return {
            "capital_current": 0.0,
            "capital_peak": 0.0,
            "daily_pnl": 0.0,
            "streak": 0,
            "daily_target_pct": 2.0,
            "daily_stop_pct": 3.0
        }

    def _load_capital_state(self):
        data = self._load_json(CAPITAL_STATE_FILE, self._default_capital_state())
        if not isinstance(data, dict):
            data = self._default_capital_state()
        for k, v in self._default_capital_state().items():
            data.setdefault(k, v)
        return data

    def _load_journal(self):
        data = self._load_json(JOURNAL_FILE, [])
        return data if isinstance(data, list) else []

    def _result_value(self, trade):
        return str(trade.get("result", "")).upper()

    def _today_key(self):
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _trade_date_key(self, trade):
        return str(trade.get("date") or self._today_key())

    def _valid_trades(self, journal):
        return [t for t in journal if self._result_value(t) in ("WIN", "LOSS")]

    def _compute_streak(self, valid_trades):
        if not valid_trades:
            return 0
        streak = 0
        for trade in valid_trades:
            result = self._result_value(trade)
            if result == "WIN":
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif result == "LOSS":
                if streak <= 0:
                    streak -= 1
                else:
                    break
        return streak

    def _compute_daily_pnl(self, valid_trades, capital_current):
        today = self._today_key()
        todays = [t for t in valid_trades if self._trade_date_key(t) == today]
        if not todays or capital_current <= 0:
            return 0.0
        unit_risk = max(1.0, round(capital_current * 0.01, 2))
        pnl = 0.0
        for trade in todays:
            pnl += unit_risk if self._result_value(trade) == "WIN" else -unit_risk
        return round(pnl, 2)

    def update(self):
        state = self._load_capital_state()
        journal = self._load_journal()
        valid = self._valid_trades(journal)
        capital_current = float(state.get("capital_current", 0.0) or 0.0)
        capital_peak = float(state.get("capital_peak", 0.0) or 0.0)
        state["daily_pnl"] = self._compute_daily_pnl(valid, capital_current)
        state["streak"] = self._compute_streak(valid)
        if capital_current > capital_peak:
            capital_peak = capital_current
        state["capital_peak"] = round(capital_peak, 2)
        self._save_json(CAPITAL_STATE_FILE, state)
        return state
