import json
import os

DATA_DIR = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
os.makedirs(DATA_DIR, exist_ok=True)

MEMORY_FILE = os.path.join(DATA_DIR, "alpha_hive_memory_context.json")


class MemoryEngine:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _save(self):
        tmp = MEMORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, MEMORY_FILE)

    def _rsi_bucket(self, rsi):
        try:
            r = float(rsi)
        except Exception:
            return "unknown"
        if r <= 35:
            return "oversold"
        if r >= 65:
            return "overbought"
        if 45 <= r <= 55:
            return "neutral"
        return "mid"

    def _hour_bucket(self, time_str):
        try:
            text = str(time_str).strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def build_context_id(self, asset, strategy_name, indicators, analysis_time=None):
        regime = indicators.get("regime", "unknown")
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        breakout = "1" if indicators.get("breakout", False) else "0"
        rejection = "1" if indicators.get("rejection", False) else "0"
        pattern = indicators.get("pattern", "none")
        rsi_bucket = self._rsi_bucket(indicators.get("rsi", 50))
        hour_bucket = self._hour_bucket(analysis_time)
        return "|".join([
            str(asset or "N/A"),
            str(strategy_name or "none"),
            str(regime),
            str(trend_m1),
            str(trend_m5),
            str(pattern),
            f"rsi:{rsi_bucket}",
            f"bo:{breakout}",
            f"rej:{rejection}",
            f"h:{hour_bucket}",
        ])

    def register_context(self, asset, strategy_name, indicators, analysis_time=None):
        context_id = self.build_context_id(asset, strategy_name, indicators, analysis_time)
        if context_id not in self.data:
            self.data[context_id] = {
                "context_id": context_id,
                "asset": asset,
                "strategy": strategy_name,
                "regime": indicators.get("regime", "unknown"),
                "total": 0,
                "wins": 0,
                "loss": 0,
            }
            self._save()
        return context_id

    def register_result(self, context_id, result):
        if not context_id or context_id not in self.data:
            return
        normalized = str(result).upper()
        if normalized not in ("WIN", "LOSS"):
            return
        row = self.data[context_id]
        row["total"] += 1
        if normalized == "WIN":
            row["wins"] += 1
        else:
            row["loss"] += 1
        self._save()

    def context_stats(self, context_id):
        row = self.data.get(context_id)
        if not row:
            return {"context_id": context_id, "total": 0, "wins": 0, "loss": 0, "winrate": 0.0}
        total = int(row.get("total", 0))
        wins = int(row.get("wins", 0))
        loss = int(row.get("loss", 0))
        winrate = round((wins / total) * 100, 2) if total > 0 else 0.0
        return {**row, "winrate": winrate}

    def get_memory_boost(self, context_id):
        stats = self.context_stats(context_id)
        total = stats.get("total", 0)
        winrate = stats.get("winrate", 0.0)

        if total < 8:
            return 0.0, "Memória sem amostra suficiente"
        if winrate >= 70:
            return 0.28, "Memória muito favorável"
        if winrate >= 60:
            return 0.14, "Memória favorável"
        if winrate <= 35:
            return -0.20, "Memória desfavorável"
        if winrate <= 42:
            return -0.10, "Memória levemente desfavorável"
        return 0.0, "Memória neutra"
