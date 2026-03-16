class LearningEngine:

    def __init__(self):

        self.asset_stats = {}
        self.total_trades = 0
        self.total_wins = 0


    # =================================
    # bônus adaptativo para o score
    # =================================

    def get_adaptive_bonus(self, asset):

        stats = self.asset_stats.get(asset)

        if not stats:
            return 0

        total = stats["total"]
        wins = stats["wins"]

        if total < 5:
            return 0

        winrate = wins / total

        if winrate > 0.65:
            return 2

        if winrate > 0.55:
            return 1

        if winrate < 0.40:
            return -1

        return 0


    # =================================
    # atualizar estatísticas
    # =================================

    def update_stats(self, signals):

        # mantido por compatibilidade
        pass


    # =================================
    # registrar resultado
    # =================================

    def register_result(self, signal, result_data):

        asset = signal.get("asset")

        if asset not in self.asset_stats:

            self.asset_stats[asset] = {
                "wins": 0,
                "total": 0
            }

        self.asset_stats[asset]["total"] += 1

        if result_data.get("result") == "WIN":

            self.asset_stats[asset]["wins"] += 1
            self.total_wins += 1

        self.total_trades += 1


    # =================================
    # estatísticas gerais
    # =================================

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
