import json
import os

STATE_FILE = "/tmp/nexus_learning.json"


class LearningEngine:
    def dynamic_signal_limit(self):
    return 5
    
    def should_filter_asset(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return False

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        wins = int(data.get("wins", 0))
        loss = int(data.get("loss", 0))
        total = wins + loss

        if total < 8:
            return False

        winrate = wins / total if total else 0.0
        return winrate < 0.35
    
    def __init__(self):
        self.memory = self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False)

    def _ensure_asset(self, asset):
        if not asset:
            return None
        if asset not in self.memory:
            self.memory[asset] = {"wins": 0, "loss": 0}
        return asset

    def register_result(self, signal, result):
        asset = self._ensure_asset(signal.get("asset"))
        if not asset:
            return

        win = result.get("win")
        if win is None:
            outcome = str(result.get("result", "")).upper()
            if outcome == "WIN":
                win = True
            elif outcome == "LOSS":
                win = False
            else:
                return

        if win:
            self.memory[asset]["wins"] += 1
        else:
            self.memory[asset]["loss"] += 1

        self._save()

    def get_score_boost(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return 0.0

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        total = data["wins"] + data["loss"]

        if total < 5:
            return 0.0

        winrate = data["wins"] / total
        return round((winrate - 0.5) * 2, 2)

    def get_calibration_profile(self, asset=None):
        if asset:
            asset = self._ensure_asset(asset)
            data = self.memory.get(asset, {"wins": 0, "loss": 0})
            total = data["wins"] + data["loss"]

            if total < 5:
                return {
                    "confidence_factor": 1.0,
                    "aggressiveness": 1.0,
                    "min_score": 3.0,
                    "max_signals": 2,
                    "mode": "base"
                }

            winrate = data["wins"] / total
            confidence_factor = 0.8 + (winrate * 0.4)
            aggressiveness = 0.9 + (winrate * 0.3)

            if winrate >= 0.65:
                min_score = 2.8
                max_signals = 3
                mode = "confiante"
            elif winrate <= 0.40:
                min_score = 3.4
                max_signals = 1
                mode = "cautela"
            else:
                min_score = 3.0
                max_signals = 2
                mode = "equilibrado"

            return {
                "confidence_factor": round(confidence_factor, 2),
                "aggressiveness": round(aggressiveness, 2),
                "min_score": round(min_score, 2),
                "max_signals": max_signals,
                "mode": mode
            }

        total_wins = 0
        total_loss = 0
        for data in self.memory.values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total = total_wins + total_loss
        if total < 5:
            return {
                "confidence_factor": 1.0,
                "aggressiveness": 1.0,
                "min_score": 3.0,
                "max_signals": 2,
                "mode": "base"
            }

        winrate = total_wins / total
        confidence_factor = 0.8 + (winrate * 0.4)
        aggressiveness = 0.9 + (winrate * 0.3)

        if winrate >= 0.65:
            min_score = 2.8
            max_signals = 3
            mode = "confiante"
        elif winrate <= 0.40:
            min_score = 3.4
            max_signals = 1
            mode = "cautela"
        else:
            min_score = 3.0
            max_signals = 2
            mode = "equilibrado"

        return {
            "confidence_factor": round(confidence_factor, 2),
            "aggressiveness": round(aggressiveness, 2),
            "min_score": round(min_score, 2),
            "max_signals": max_signals,
            "mode": mode
        }

    def dynamic_minimum_score(self):
        profile = self.get_calibration_profile()
        return profile.get("min_score", 3.0)

    def get_adaptive_bonus(self, asset, *args, **kwargs):
        boost = self.get_score_boost(asset)
        if boost > 0.2:
            return boost, "Ativo favorável"
        if boost < -0.2:
            return boost, "Ativo fraco"
        return boost, "Histórico insuficiente"

    def should_pause_asset_temporarily(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return False

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        wins = int(data.get("wins", 0))
        loss = int(data.get("loss", 0))
        total = wins + loss

        if total < 6:
            return False

        winrate = wins / total if total else 0.0
        return loss >= 5 and winrate < 0.35

    def get_rigor_penalty(self):
        total_wins = 0
        total_loss = 0
        for data in self.memory.values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total = total_wins + total_loss
        if total < 8:
            return 0.0

        winrate = total_wins / total if total else 0.0

        if winrate < 0.40:
            return 0.45
        if winrate > 0.65:
            return -0.10
        return 0.0

    def get_global_bias(self):
        total_wins = 0
        total_loss = 0
        for data in self.memory.values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total = total_wins + total_loss
        if total < 8:
            return 0.0, "Sem memória global suficiente"

        winrate = total_wins / total if total else 0.0
        if winrate >= 0.65:
            return 0.2, "Fase global positiva"
        if winrate <= 0.40:
            return -0.2, "Fase global cautelosa"
        return 0.0, "Fase global neutra"

    def update_stats(self, signals):
        return
