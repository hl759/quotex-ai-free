import json
import os
from storage_paths import DATA_DIR, migrate_file
from json_safe import safe_dump
from state_store import get_state_store

from config import DEFAULT_PAYOUT

os.makedirs(DATA_DIR, exist_ok=True)

JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")
migrate_file(JOURNAL_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_journal.json")])
COLLECTION_NAME = "journal_trades"


class JournalManager:
    def __init__(self):
        self.store = get_state_store()
        if not os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
                safe_dump([], f)
        self._bootstrap_store_from_file()

    def _bootstrap_store_from_file(self):
        if self.store.list_collection(COLLECTION_NAME, limit=1):
            return
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            return
        if not isinstance(rows, list):
            return
        for trade in reversed(rows[:4000]):
            self.store.append_unique_item(COLLECTION_NAME, self._trade_id(trade), trade, created_at=str(trade.get("date") or ""))

    def _load(self):
        rows = self.store.list_collection(COLLECTION_NAME, limit=4000)
        if rows:
            return rows
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            return []
        return []

    def _save(self, data):
        tmp = JOURNAL_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(data, f)
        os.replace(tmp, JOURNAL_FILE)

    def _trade_id(self, trade):
        return f"{trade.get('asset')}-{trade.get('signal')}-{trade.get('analysis_time')}-{trade.get('entry_time')}-{trade.get('expiration')}"

    def _valid_trades(self):
        return [t for t in self._load() if str(t.get("result", "")).upper() in ("WIN", "LOSS")]

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _extract_hour_bucket(self, trade):
        try:
            analysis_time = str(trade.get("analysis_time", "")).strip()
            if ":" not in analysis_time:
                return None
            hour = int(analysis_time.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else None
        except Exception:
            return None

    def add_trade(self, trade):
        trade_id = self._trade_id(trade)
        inserted = self.store.append_unique_item(COLLECTION_NAME, trade_id, trade, created_at=str(trade.get("date") or ""))
        if inserted:
            data = self._load()
            if len(data) > 4000:
                data = data[:4000]
            self._save(data)

    def _economic_stats(self, valid):
        if not valid:
            return {
                "total_pnl": 0.0,
                "expectancy_r": 0.0,
                "avg_payout": round(DEFAULT_PAYOUT, 4),
                "breakeven_winrate": round((1 / (1 + DEFAULT_PAYOUT)) * 100, 2),
                "profit_factor": 0.0,
            }
        pnls = [self._safe_float(t.get("gross_pnl"), 0.0) for t in valid]
        rs = [self._safe_float(t.get("gross_r"), 0.0) for t in valid]
        payouts = [max(0.0, self._safe_float(t.get("payout"), DEFAULT_PAYOUT)) for t in valid]
        avg_payout = sum(payouts) / len(payouts) if payouts else DEFAULT_PAYOUT
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        return {
            "total_pnl": round(sum(pnls), 2),
            "expectancy_r": round(sum(rs) / len(rs), 4) if rs else 0.0,
            "avg_payout": round(avg_payout, 4),
            "breakeven_winrate": round((1 / (1 + avg_payout)) * 100, 2) if avg_payout > 0 else 100.0,
            "profit_factor": round(profit_factor, 3),
        }

    def stats(self):
        valid = self._valid_trades()
        if not valid:
            return {"total": 0, "wins": 0, "loss": 0, "winrate": 0.0, **self._economic_stats(valid)}
        wins = sum(1 for t in valid if str(t.get("result", "")).upper() == "WIN")
        total = len(valid)
        return {
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2),
            **self._economic_stats(valid)
        }

    def asset_stats(self, asset):
        valid = [t for t in self._valid_trades() if t.get("asset") == asset]
        if not valid:
            return {"asset": asset, "total": 0, "wins": 0, "loss": 0, "winrate": 0.0, **self._economic_stats(valid)}
        wins = sum(1 for t in valid if str(t.get("result", "")).upper() == "WIN")
        total = len(valid)
        return {
            "asset": asset,
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2),
            **self._economic_stats(valid)
        }

    def best_assets(self):
        grouped = {}
        for t in self._valid_trades():
            asset = t.get("asset", "N/A")
            grouped.setdefault(asset, [])
            grouped[asset].append(t)

        result = []
        for asset, rows in grouped.items():
            total = len(rows)
            wins = sum(1 for t in rows if str(t.get("result", "")).upper() == "WIN")
            row = {
                "asset": asset,
                "total": total,
                "wins": wins,
                "winrate": round((wins / total) * 100, 2) if total else 0.0,
                **self._economic_stats(rows)
            }
            result.append(row)

        result = [r for r in result if r["total"] >= 1]
        result.sort(key=lambda x: (x.get("expectancy_r", 0.0), x["winrate"], x["total"]), reverse=True)
        return result[:10]

    def hour_stats(self, hour_bucket):
        valid = [t for t in self._valid_trades() if self._extract_hour_bucket(t) == hour_bucket]
        if not valid:
            return {"hour": hour_bucket, "total": 0, "wins": 0, "loss": 0, "winrate": 0.0, **self._economic_stats(valid)}
        wins = sum(1 for t in valid if str(t.get("result", "")).upper() == "WIN")
        total = len(valid)
        return {
            "hour": hour_bucket,
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2),
            **self._economic_stats(valid)
        }

    def best_hours(self):
        grouped = {}
        for t in self._valid_trades():
            hb = self._extract_hour_bucket(t)
            if not hb:
                continue
            grouped.setdefault(hb, [])
            grouped[hb].append(t)

        result = []
        for hour, rows in grouped.items():
            wins = sum(1 for t in rows if str(t.get("result", "")).upper() == "WIN")
            total = len(rows)
            row = {
                "hour": hour,
                "total": total,
                "wins": wins,
                "winrate": round((wins / total) * 100, 2) if total else 0.0,
                **self._economic_stats(rows)
            }
            result.append(row)

        result = [r for r in result if r["total"] >= 1]
        result.sort(key=lambda x: (x.get("expectancy_r", 0.0), x["winrate"], x["total"]), reverse=True)
        return result[:10]

    def recent_asset_results(self, asset, limit=6):
        valid = [str(t.get("result", "")).upper() for t in self._valid_trades() if t.get("asset") == asset]
        return valid[:limit]

    def recent_global_results(self, limit=12):
        valid = [str(t.get("result", "")).upper() for t in self._valid_trades()]
        return valid[:limit]
