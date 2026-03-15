
class LearningEngine:

    def __init__(self):
        self.asset_stats = {}

    def update_stats(self, signals):

        for s in signals:

            asset = s["asset"]

            if asset not in self.asset_stats:

                self.asset_stats[asset] = {
                    "signals": 0
                }

            self.asset_stats[asset]["signals"] += 1
