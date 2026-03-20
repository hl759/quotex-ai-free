import json
import os

STATE_FILE = "/tmp/nexus_learning.json"

class LearningEngine:
    def __init__(self):
        self.memory = self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.memory, f)

    def register_result(self, signal, result):
        asset = signal.get("asset")
        win = result.get("win")

        if asset not in self.memory:
            self.memory[asset] = {"wins": 0, "loss": 0}

        if win:
            self.memory[asset]["wins"] += 1
        else:
            self.memory[asset]["loss"] += 1

        self._save()

    def get_score_boost(self, asset):
        data = self.memory.get(asset, {"wins":0,"loss":0})
        total = data["wins"] + data["loss"]
        if total < 5:
            return 0

        winrate = data["wins"] / total
        return (winrate - 0.5) * 2
