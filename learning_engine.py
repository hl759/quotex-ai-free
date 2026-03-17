class LearningEngine:
    def __init__(self):
        self.asset_stats = {}
        self.total_trades = 0
        self.total_wins = 0

    # Compatível com chamadas como:
    # bonus, reason = get_adaptive_bonus(asset)
    # bonus, reason = get_adaptive_bonus(asset, score)
    # bonus, reason = get_adaptive_bonus(asset, score, anything)
    def get_adaptive_bonus(self, asset, *args, **kwargs):
        stats = self.asset_stats.get(asset)

        if not stats:
            return 0, "Sem histórico suficiente"

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

    # Mantido por compatibilidade
    def update_stats(self, signals):
        return

    def register_result(self, signal, result_data):
        asset = signal.get("asset")
        if not asset:
            return

        if asset not in self.asset_stats:
            self.asset_stats[asset] = {
                "wins": 0,
                "total": 0
            }

        self.asset_stats[asset]["total"] += 1
        self.total_trades += 1

        if result_data.get("result") == "WIN":
            self.asset_stats[asset]["wins"] += 1
            self.total_wins += 1

    def get_stats(self):
        if self.total_trades == 0:
            return {
                "total": 0,
                "wins": 0,
                "loss": 0,
                "winrate": 0
            }

        winrate = (self.total_wins / self.total_trades) * 100

        return {
            "total": self.total_trades,
            "wins": self.total_wins,
            "loss": self.total_trades - self.total_wins,
            "winrate": round(winrate, 2)
        }
