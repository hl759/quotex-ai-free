import json
import os

DATA_DIR = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
os.makedirs(DATA_DIR, exist_ok=True)

ADAPTIVE_FILE = os.path.join(DATA_DIR, "alpha_hive_adaptive_weights.json")


class AdaptiveEngine:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(ADAPTIVE_FILE):
                with open(ADAPTIVE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _save(self):
        tmp = ADAPTIVE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, ADAPTIVE_FILE)

    def _key(self, strategy_name, regime):
        return f"{strategy_name}|{regime}"

    def ensure_profile(self, strategy_name, regime):
        key = self._key(strategy_name, regime)
        if key not in self.data:
            self.data[key] = {
                "strategy": strategy_name,
                "regime": regime,
                "weight": 1.0,
                "total": 0,
                "wins": 0,
                "loss": 0,
                "status": "neutral"
            }
            self._save()
        return self.data[key]

    def register_result(self, strategy_name, regime, result):
        if not strategy_name or strategy_name == "none":
            return

        profile = self.ensure_profile(strategy_name, regime)
        normalized = str(result).upper()
        if normalized not in ("WIN", "LOSS"):
            return

        profile["total"] += 1
        if normalized == "WIN":
            profile["wins"] += 1
        else:
            profile["loss"] += 1

        total = int(profile["total"])
        wins = int(profile["wins"])
        winrate = (wins / total) if total > 0 else 0.0

        if total >= 10:
            if winrate >= 0.66:
                profile["weight"] = min(1.28, float(profile["weight"]) + 0.04)
                profile["status"] = "favored"
            elif winrate >= 0.58:
                profile["weight"] = min(1.18, float(profile["weight"]) + 0.02)
                profile["status"] = "slightly_favored"
            elif winrate <= 0.38:
                profile["weight"] = max(0.72, float(profile["weight"]) - 0.05)
                profile["status"] = "reduced"
            elif winrate <= 0.45:
                profile["weight"] = max(0.84, float(profile["weight"]) - 0.02)
                profile["status"] = "slightly_reduced"
            else:
                profile["status"] = "neutral"

        self._save()

    def get_weight(self, strategy_name, regime):
        profile = self.ensure_profile(strategy_name, regime)
        return float(profile.get("weight", 1.0))

    def get_reason(self, strategy_name, regime):
        profile = self.ensure_profile(strategy_name, regime)
        total = int(profile.get("total", 0))
        wins = int(profile.get("wins", 0))
        status = profile.get("status", "neutral")

        if total < 10:
            return "Peso adaptativo neutro"

        winrate = round((wins / total) * 100, 2) if total else 0.0

        if status == "favored":
            return f"Estratégia favorecida por performance ({winrate}%)"
        if status == "slightly_favored":
            return f"Estratégia levemente favorecida ({winrate}%)"
        if status == "reduced":
            return f"Estratégia reduzida por performance ({winrate}%)"
        if status == "slightly_reduced":
            return f"Estratégia levemente reduzida ({winrate}%)"
        return f"Estratégia adaptativamente neutra ({winrate}%)"

    def should_soft_block(self, strategy_name, regime):
        profile = self.ensure_profile(strategy_name, regime)
        total = int(profile.get("total", 0))
        loss = int(profile.get("loss", 0))
        wins = int(profile.get("wins", 0))
        if total < 14:
            return False
        winrate = (wins / total) if total else 0.0
        return winrate <= 0.30 and loss >= 8
