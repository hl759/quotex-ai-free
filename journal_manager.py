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

    def add_trade(self, trade):
        data = self._load()

        # evita duplicar a mesma operação em scans repetidos
        trade_id = f"{trade.get('asset')}-{trade.get('signal')}-{trade.get('analysis_time')}-{trade.get('entry_time')}"
        for item in data:
            item_id = f"{item.get('asset')}-{item.get('signal')}-{item.get('analysis_time')}-{item.get('entry_time')}"
            if item_id == trade_id:
                return

        data.insert(0, trade)

        if len(data) > 500:
            data = data[:500]

        self._save(data)

    def stats(self):
        trades = self._load()

        valid = [t for t in trades if t.get("result") in ("WIN", "LOSS")]

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
        trades = self._load()
        valid = [t for t in trades if t.get("asset") == asset and t.get("result") in ("WIN", "LOSS")]

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
        trades = self._load()
        valid = [t for t in trades if t.get("result") in ("WIN", "LOSS")]

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
        for asset, info in grouped.items():
            total = info["total"]
            wins = info["wins"]

            if total == 0:
                continue

            result.append({
                "asset": asset,
                "total": total,
                "wins": wins,
                "winrate": round((wins / total) * 100, 2)
            })

        # só mostra ativos com pelo menos 3 trades para não poluir cedo demais
        result = [r for r in result if r["total"] >= 3]
        result.sort(key=lambda x: (x["winrate"], x["total"]), reverse=True)

        return result[:10]
