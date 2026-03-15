
class LearningEngine:

    def __init__(self):
        self.stats = {}

    def update_stats(self, signals):

        for s in signals:
            asset = s["asset"]

            if asset not in self.stats:
                self.stats[asset] = {"signals":0}

            self.stats[asset]["signals"] += 1
