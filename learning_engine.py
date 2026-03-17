from journal_manager import JournalManager


class LearningEngine:
    def __init__(self):
        self.journal = JournalManager()

    def get_adaptive_bonus(self, asset, *args, **kwargs):
        stats = self.journal.asset_stats(asset)

        total = stats.get("total", 0)
        wins = stats.get("wins", 0)

        if total < 5:
            return 0, "Histórico insuficiente"

        winrate = wins / total

        if winrate >= 0.65:
            return 2, "Bônus adaptativo forte"
        if winrate >= 0.55:
            return 1, "Bônus adaptativo leve"
        if winrate <= 0.40:
            return -1, "Penalidade adaptativa"

        return 0, "Neutro"

    def update_stats(self, signals):
        return

    def register_result(self, signal, result_data):
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
            "result": result_data.get("result", "UNKNOWN"),
        }

        self.journal.add_trade(trade)

    def get_stats(self):
        return self.journal.stats()
