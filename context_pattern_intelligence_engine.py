import json
import os
from storage_paths import DATA_DIR, migrate_file

os.makedirs(DATA_DIR, exist_ok=True)
JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")
migrate_file(JOURNAL_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_journal.json")])


class ContextPatternIntelligenceEngine:
    def _load_journal(self):
        try:
            if os.path.exists(JOURNAL_FILE):
                with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
        except Exception:
            pass
        return []

    def _result_value(self, row):
        return str(row.get("result", "")).upper()

    def _hour_bucket(self, analysis_time):
        try:
            text = str(analysis_time or "").strip()
            if ":" not in text:
                return "unknown"
            hh = int(text.split(":")[0])
            return f"{hh:02d}:00" if 0 <= hh <= 23 else "unknown"
        except Exception:
            return "unknown"

    def _strategy_family(self, strategy_name):
        name = str(strategy_name or "none")
        if name.startswith("trend"):
            return "trend"
        if name.startswith("reversal"):
            return "reversal"
        if name.startswith("scalp"):
            return "scalp"
        return name

    def _valid_trades(self):
        return [t for t in self._load_journal() if self._result_value(t) in ("WIN", "LOSS")]

    def _match_rows(self, asset, regime, strategy_name, analysis_time):
        target_hour = self._hour_bucket(analysis_time)
        target_family = self._strategy_family(strategy_name)
        rows = []
        for t in self._valid_trades():
            if str(t.get("asset", "")) != str(asset):
                continue
            similarity = 0
            if str(t.get("regime", "unknown")) == str(regime):
                similarity += 2
            if self._hour_bucket(t.get("analysis_time")) == target_hour and target_hour != "unknown":
                similarity += 2
            trade_strategy = str(t.get("strategy_name", "none"))
            trade_family = self._strategy_family(trade_strategy)
            if trade_strategy == str(strategy_name):
                similarity += 3
            elif trade_family == target_family:
                similarity += 1
            rows.append({"result": self._result_value(t), "similarity": similarity})
        rows.sort(key=lambda x: x["similarity"], reverse=True)
        return rows

    def get_adjustment(self, asset, regime, strategy_name, analysis_time=None):
        rows = self._match_rows(asset, regime, strategy_name, analysis_time)
        if not rows:
            return {"score_boost": 0.0, "confidence_shift": 0, "reason": "Context Pattern neutro (sem histórico)", "mode": "neutral", "sample": 0, "winrate": 0.0}

        strong = [r for r in rows if r["similarity"] >= 4]
        medium = [r for r in rows if r["similarity"] >= 2]
        if len(strong) >= 10:
            relevant = strong[:40]
        elif len(medium) >= 10:
            relevant = medium[:50]
        else:
            relevant = rows[:max(10, min(60, len(rows)))]

        total = len(relevant)
        wins = sum(1 for r in relevant if r["result"] == "WIN")
        winrate = round((wins / total) * 100, 2) if total > 0 else 0.0

        if total < 10:
            return {"score_boost": 0.0, "confidence_shift": 0, "reason": "Context Pattern com pouca amostra", "mode": "neutral", "sample": total, "winrate": winrate}
        if winrate >= 70:
            return {"score_boost": 0.24, "confidence_shift": 5, "reason": f"Context Pattern muito favorável ({winrate}%)", "mode": "favored", "sample": total, "winrate": winrate}
        if winrate >= 60:
            return {"score_boost": 0.12, "confidence_shift": 2, "reason": f"Context Pattern favorável ({winrate}%)", "mode": "slightly_favored", "sample": total, "winrate": winrate}
        if winrate <= 35:
            return {"score_boost": -0.20, "confidence_shift": -5, "reason": f"Context Pattern desfavorável ({winrate}%)", "mode": "reduced", "sample": total, "winrate": winrate}
        if winrate <= 42:
            return {"score_boost": -0.08, "confidence_shift": -2, "reason": f"Context Pattern levemente desfavorável ({winrate}%)", "mode": "slightly_reduced", "sample": total, "winrate": winrate}
        return {"score_boost": 0.0, "confidence_shift": 0, "reason": f"Context Pattern neutro ({winrate}%)", "mode": "neutral", "sample": total, "winrate": winrate}
