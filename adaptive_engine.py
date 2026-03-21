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
                "loss": 0
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

        total = profile["total"]
        wins = profile["wins"]
        winrate = wins / total if total > 0 else 0.0

        if total >= 10:
            if winrate >= 0.65:
                profile["weight"] = min(1.22, profile["weight"] + 0.03)
            elif winrate <= 0.40:
                profile["weight"] = max(0.82, profile["weight"] - 0.03)

        self._save()

    def get_weight(self, strategy_name, regime):
        profile = self.ensure_profile(strategy_name, regime)
        return float(profile.get("weight", 1.0))

    def get_reason(self, strategy_name, regime):
        profile = self.ensure_profile(strategy_name, regime)
        total = int(profile.get("total", 0))
        wins = int(profile.get("wins", 0))
        if total < 10:
            return "Peso adaptativo neutro"
        winrate = (wins / total) * 100 if total else 0.0
        if winrate >= 65:
            return "Estratégia adaptativamente favorecida"
        if winrate <= 40:
            return "Estratégia adaptativamente reduzida"
        return "Estratégia adaptativamente neutra"
