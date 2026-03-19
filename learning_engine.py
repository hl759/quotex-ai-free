from collections import deque
from journal_manager import JournalManager


class LearningEngine:
    def __init__(self):
        self.journal = JournalManager()
        self.recent_results = deque(maxlen=20)

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
        asset_bonus = 0
        hour_bonus = 0
        reasons = []

        asset_stats = self.journal.asset_stats(asset)
        if asset_stats.get("total", 0) >= 5:
            winrate = asset_stats.get("winrate", 0.0)
            if winrate >= 68:
                asset_bonus = 2
                reasons.append("Ativo elite")
            elif winrate >= 57:
                asset_bonus = 1
                reasons.append("Ativo favorável")
            elif winrate <= 40:
                asset_bonus = -1
                reasons.append("Ativo fraco")

        hour_bucket = self._extract_hour_bucket(*args, **kwargs)
        if hour_bucket:
            hour_stats = self.journal.hour_stats(hour_bucket)
            if hour_stats.get("total", 0) >= 5:
                winrate = hour_stats.get("winrate", 0.0)
                if winrate >= 66:
                    hour_bonus = 1
                    reasons.append("Horário forte")
                elif winrate <= 40:
                    hour_bonus = -1
                    reasons.append("Horário fraco")

        if not reasons:
            reasons.append("Histórico insuficiente")

        return asset_bonus + hour_bonus, " | ".join(reasons)

    def should_filter_asset(self, asset):
        stats = self.journal.asset_stats(asset)
        return bool(stats.get("total", 0) >= 12 and stats.get("winrate", 0.0) <= 35)

    def should_pause_asset_temporarily(self, asset):
        recent = self.journal.recent_asset_results(asset, limit=5)
        if len(recent) < 4:
            return False
        losses = sum(1 for item in recent if item == "LOSS")
        return losses >= 4

    def get_rigor_penalty(self):
        if len(self.recent_results) < 5:
            return 0
        losses = sum(1 for item in self.recent_results if item == "LOSS")
        if losses >= 4:
            return 0.8
        if losses >= 3:
            return 0.4
        return 0

    def dynamic_minimum_score(self):
        if len(self.recent_results) < 5:
            return 4.8
        wins = sum(1 for item in self.recent_results if item == "WIN")
        if wins <= 1:
            return 5.6
        if wins <= 2:
            return 5.2
        return 4.8

    def dynamic_signal_limit(self):
        if len(self.recent_results) < 5:
            return 3
        wins = sum(1 for item in self.recent_results if item == "WIN")
        return 2 if wins <= 2 else 3

    def update_stats(self, signals):
        return

    def register_result(self, signal, result_data):
        result = result_data.get("result", "UNKNOWN")
        if result in ("WIN", "LOSS"):
            self.recent_results.append(result)

        self.journal.add_trade({
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
            "result": result
        })
