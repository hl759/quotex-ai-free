import json
import os
from storage_paths import DATA_DIR, migrate_file

JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")
migrate_file(JOURNAL_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_journal.json")])


class ContextIntelligenceEngine:
    def __init__(self):
        pass

    def _load_journal(self):
        try:
            if os.path.exists(JOURNAL_FILE):
                with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
        except Exception:
            pass
        return []

    def _hour_bucket(self, time_str):
        try:
            text = str(time_str).strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def _weekday_bucket(self, weekday):
        try:
            wd = int(weekday)
        except Exception:
            return "unknown"
        names = {
            0: "monday",
            1: "tuesday",
            2: "wednesday",
            3: "thursday",
            4: "friday",
            5: "saturday",
            6: "sunday",
        }
        return names.get(wd, "unknown")

    def _trade_weekday(self, trade):
        # If weekday was not stored, infer neutral fallback
        weekday = trade.get("weekday")
        return self._weekday_bucket(weekday) if weekday is not None else "unknown"

    def _match_rows(self, asset, regime, analysis_time, weekday):
        hour_bucket = self._hour_bucket(analysis_time)
        weekday_bucket = self._weekday_bucket(weekday)

        rows = []
        for t in self._load_journal():
            result = str(t.get("result", "")).upper()
            if result not in ("WIN", "LOSS"):
                continue
            if str(t.get("asset")) != str(asset):
                continue
            if str(t.get("regime", "unknown")) != str(regime):
                continue

            similarity = 0
            if self._hour_bucket(t.get("analysis_time")) == hour_bucket:
                similarity += 1
            if self._trade_weekday(t) == weekday_bucket and weekday_bucket != "unknown":
                similarity += 1

            rows.append({
                "result": result,
                "similarity": similarity,
            })

        rows.sort(key=lambda x: x["similarity"], reverse=True)
        return rows

    def get_adjustment(self, asset, regime, analysis_time=None, weekday=None):
        rows = self._match_rows(asset, regime, analysis_time, weekday)
        if not rows:
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "reason": "Contexto sem histórico relacionado",
                "mode": "neutral"
            }

        # Prefer most similar rows, but keep a decent sample
        relevant = [r for r in rows if r["similarity"] >= 1]
        if len(relevant) < 10:
            relevant = rows[: max(10, min(30, len(rows)))]

        total = len(relevant)
        wins = sum(1 for r in relevant if r["result"] == "WIN")
        winrate = round((wins / total) * 100, 2) if total > 0 else 0.0

        if total < 10:
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "reason": "Contexto com pouca amostra",
                "mode": "neutral"
            }

        if winrate >= 68:
            return {
                "score_boost": 0.22,
                "confidence_shift": 4,
                "reason": f"Contexto muito favorável ({winrate}%)",
                "mode": "favored"
            }
        if winrate >= 58:
            return {
                "score_boost": 0.10,
                "confidence_shift": 2,
                "reason": f"Contexto favorável ({winrate}%)",
                "mode": "slightly_favored"
            }
        if winrate <= 35:
            return {
                "score_boost": -0.18,
                "confidence_shift": -5,
                "reason": f"Contexto desfavorável ({winrate}%)",
                "mode": "reduced"
            }
        if winrate <= 42:
            return {
                "score_boost": -0.08,
                "confidence_shift": -2,
                "reason": f"Contexto levemente desfavorável ({winrate}%)",
                "mode": "slightly_reduced"
            }

        return {
            "score_boost": 0.0,
            "confidence_shift": 0,
            "reason": f"Contexto neutro ({winrate}%)",
            "mode": "neutral"
        }
