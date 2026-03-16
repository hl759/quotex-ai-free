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
        data.insert(0, trade)

        if len(data) > 500:
            data = data[:500]

        self._save(data)

    def stats(self):
        trades = self._load()

        if not trades:
            return {
                "total": 0,
                "wins": 0,
                "loss": 0,
                "winrate": 0.0
            }

        wins = sum(1 for t in trades if t.get("result") == "WIN")
        total = len(trades)

        return {
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": round((wins / total) * 100, 2)
        }

    def best_assets(self):
        trades = self._load()
        grouped = {}

        for t in trades:
            asset = t.get("asset", "N/A")
            if asset not in grouped:
                grouped[asset] = {"total": 0, "wins": 0}

            grouped[asset]["total"] += 1
            if t.get("result") == "WIN":
                grouped[asset]["wins"] += 1

        result = []
        for asset, info in grouped.items():
            if info["total"] == 0:
                continue
            winrate = round((info["wins"] / info["total"]) * 100, 2)
            result.append({
                "asset": asset,
                "total": info["total"],
                "wins": info["wins"],
                "winrate": winrate
            })

        result.sort(key=lambda x: x["winrate"], reverse=True)
        return result[:10]
