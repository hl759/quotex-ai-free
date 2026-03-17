import json
import os

JOURNAL_FILE = "/tmp/nexus_journal.json"


class JournalManager:
    def __init__(self):
        if not os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _load(self):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, data):
        tmp = JOURNAL_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, JOURNAL_FILE)

    def _trade_id(self, trade):
        return (
            f"{trade.get('asset')}-"
            f"{trade.get('signal')}-"
            f"{trade.get('analysis_time')}-"
            f"{trade.get('entry_time')}-"
            f"{trade.get('expiration')}"
        )

    def _valid_trades(self):
        trades = self._load()
        return [t for t in trades if t.get("result") in ("WIN", "LOSS")]

    def _extract_hour_bucket(self, trade):
        try:
            time_value = trade.get("analysis_time", "")
            if not time_value or ":" not in time_value:
                return None

            hour = int(str(time_value).split(":")[0])
            if hour < 0 or hour > 23:
                return None

            return f"{hour:02d}:00"
        except Exception:
            return None

    def add_trade(self, trade):
        data = self._load()

        incoming_id = self._trade_id(trade)
        for item in data:
            if self._trade_id(item) == incoming_id:
                return

        data.insert(0, trade)

        if len(data) > 1000:
            data = data[:1000]

        self._save(data)

    def stats(self):
        valid = self._valid_trades()

        if not valid:
            return {
                "total": 0,
                "wins": 0,
                "loss": 0,
                "winrate": 0.0
            }

        wins = sum(1 for t in valid if t.get("result") == "WIN")
        total = len(valid)

        return {
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2)
        }

    def asset_stats(self, asset):
        valid = [t for t in self._valid_trades() if t.get("asset") == asset]

        if not valid:
            return {
                "asset": asset,
                "total": 0,
                "wins": 0,
                "loss": 0,
                "winrate": 0.0
            }

        wins = sum(1 for t in valid if t.get("result") == "WIN")
        total = len(valid)

        return {
            "asset": asset,
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2)
        }

    def best_assets(self):
        valid = self._valid_trades()
        grouped = {}

        for t in valid:
            asset = t.get("asset", "N/A")

            if asset not in grouped:
                grouped[asset] = {
                    "asset": asset,
                    "total": 0,
                    "wins": 0
                }

            grouped[asset]["total"] += 1
            if t.get("result") == "WIN":
                grouped[asset]["wins"] += 1

        result = []
        for _, info in grouped.items():
            total = info["total"]
            wins = info["wins"]

            if total == 0:
                continue

            result.append({
                "asset": info["asset"],
                "total": total,
                "wins": wins,
                "winrate": round((wins / total) * 100, 2)
            })

        result = [r for r in result if r["total"] >= 3]
        result.sort(key=lambda x: (x["winrate"], x["total"]), reverse=True)

        return result[:10]

    def hour_stats(self, hour_bucket):
        valid = []
        for trade in self._valid_trades():
            if self._extract_hour_bucket(trade) == hour_bucket:
                valid.append(trade)

        if not valid:
            return {
                "hour": hour_bucket,
                "total": 0,
                "wins": 0,
                "loss": 0,
                "winrate": 0.0
            }

        wins = sum(1 for t in valid if t.get("result") == "WIN")
        total = len(valid)

        return {
            "hour": hour_bucket,
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2)
        }

    def best_hours(self):
        valid = self._valid_trades()
        grouped = {}

        for trade in valid:
            hour_bucket = self._extract_hour_bucket(trade)
            if not hour_bucket:
                continue

            if hour_bucket not in grouped:
                grouped[hour_bucket] = {
                    "hour": hour_bucket,
                    "total": 0,
                    "wins": 0
                }

            grouped[hour_bucket]["total"] += 1
            if trade.get("result") == "WIN":
                grouped[hour_bucket]["wins"] += 1

        result = []
        for _, info in grouped.items():
            total = info["total"]
            wins = info["wins"]

            if total == 0:
                continue

            result.append({
                "hour": info["hour"],
                "total": total,
                "wins": wins,
                "winrate": round((wins / total) * 100, 2)
            })

        result = [r for r in result if r["total"] >= 3]
        result.sort(key=lambda x: (x["winrate"], x["total"]), reverse=True)

        return result[:10]

    def recent_trades(self, limit=20):
        return self._valid_trades()[:limit]
