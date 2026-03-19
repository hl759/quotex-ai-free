from collections import deque
from journal_manager import JournalManager

class LearningEngine:
    def __init__(self):
        self.journal = JournalManager()
        self.recent_results = deque(maxlen=30)

    def _extract_hour_bucket(self, *args, **kwargs):
        candidates = list(args)
        if "hour" in kwargs:
            candidates.append(kwargs.get("hour"))
        for value in candidates:
            try:
                if value is None:
                    continue
                text = str(value).strip()
                hour = int(text.split(":")[0] if ":" in text else text)
                if 0 <= hour <= 23:
                    return f"{hour:02d}:00"
            except Exception:
                continue
        return None

    def get_adaptive_bonus(self, asset, *args, **kwargs):
        asset_bonus = 0.0
        hour_bonus = 0.0
        reasons = []

        asset_stats = self.journal.asset_stats(asset)
        if asset_stats.get("total", 0) >= 6:
            winrate = asset_stats.get("winrate", 0.0)
            if winrate >= 68:
                asset_bonus = 1.4
                reasons.append("Ativo forte")
            elif winrate >= 58:
                asset_bonus = 0.8
                reasons.append("Ativo favorável")
            elif winrate <= 38:
                asset_bonus = -0.8
                reasons.append("Ativo fraco")

        hour_bucket = self._extract_hour_bucket(*args, **kwargs)
        if hour_bucket:
            hour_stats = self.journal.hour_stats(hour_bucket)
            if hour_stats.get("total", 0) >= 6:
                winrate = hour_stats.get("winrate", 0.0)
                if winrate >= 66:
                    hour_bonus = 0.9
                    reasons.append("Horário forte")
                elif winrate <= 38:
                    hour_bonus = -0.7
                    reasons.append("Horário fraco")

        if not reasons:
            reasons.append("Histórico insuficiente")

        return round(asset_bonus + hour_bonus, 2), " | ".join(reasons)

    def should_filter_asset(self, asset):
        stats = self.journal.asset_stats(asset)
        return bool(stats.get("total", 0) >= 14 and stats.get("winrate", 0.0) <= 30)

    def should_pause_asset_temporarily(self, asset):
        recent = self.journal.recent_asset_results(asset, limit=6)
        if len(recent) < 5:
            return False
        losses = sum(1 for x in recent if x == "LOSS")
        return losses >= 5

    def get_rigor_penalty(self):
        recent = self.journal.recent_global_results(limit=10)
        if len(recent) < 6:
            return 0.0
        losses = sum(1 for x in recent if x == "LOSS")
        wins = sum(1 for x in recent if x == "WIN")

        if losses >= 7:
            return 0.6
        if losses >= 6:
            return 0.45
        if wins >= 7:
            return -0.15
        return 0.0

    def get_global_bias(self):
        recent = self.journal.recent_global_results(limit=12)
        if len(recent) < 6:
            return 0.0, "Sem memória global suficiente"
        losses = sum(1 for x in recent if x == "LOSS")
        wins = sum(1 for x in recent if x == "WIN")
        if wins >= losses + 3:
            return 0.25, "Fase global positiva"
        if losses >= wins + 3:
            return -0.25, "Fase global cautelosa"
        return 0.0, "Fase global neutra"

    def update_stats(self, signals):
        return

    def register_result(self, signal, result_data):
        result = result_data.get("result", "UNKNOWN")
        if result in ("WIN", "LOSS"):
            self.recent_results.append(result)

        trade = {
            "asset": signal.get("asset"),
            "signal": signal.get("signal"),
            "score": signal.get("score", 0),
            "confidence": signal.get("confidence", 0),
            "provider": signal.get("provider", "auto"),
            "analysis_time": signal.get("analysis_time", "--:--"),
            "entry_time": signal.get("entry_time", "--:--"),
            "expiration": signal.get("expiration", "--:--"),
            "entry_price": result_data.get("entry_price"),
            "exit_price": result_data.get("exit_price"),
            "result": result,
        }
        self.journal.add_trade(trade)
