import json
import os
from storage_paths import DATA_DIR, migrate_file

os.makedirs(DATA_DIR, exist_ok=True)

STRATEGY_LAB_FILE = os.path.join(DATA_DIR, "alpha_hive_strategy_lab.json")
migrate_file(STRATEGY_LAB_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_strategy_lab.json")])


class StrategyEvolutionEngine:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            if os.path.exists(STRATEGY_LAB_FILE):
                with open(STRATEGY_LAB_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def refresh(self):
        self.data = self._load()

    def _parse_setup_id(self, setup_id):
        parts = str(setup_id).split("|")
        parsed = {
            "asset": parts[0] if len(parts) > 0 else "N/A",
            "strategy": parts[1] if len(parts) > 1 else "none",
            "regime": parts[2] if len(parts) > 2 else "unknown",
            "trend_m1": parts[3] if len(parts) > 3 else "neutral",
            "trend_m5": parts[4] if len(parts) > 4 else "neutral",
            "pattern": parts[5] if len(parts) > 5 else "none",
            "breakout": "bo:1" in parts,
            "rejection": "rej:1" in parts,
        }
        for p in parts:
            if p.startswith("h:"):
                parsed["hour"] = p.replace("h:", "")
            if p.startswith("bo:"):
                parsed["breakout"] = p.endswith("1")
            if p.startswith("rej:"):
                parsed["rejection"] = p.endswith("1")
        return parsed

    def _related_rows(self, asset, strategy_name, indicators):
        regime = indicators.get("regime", "unknown")
        pattern = indicators.get("pattern", "none")
        breakout = bool(indicators.get("breakout", False))
        rejection = bool(indicators.get("rejection", False))

        rows = []
        for setup_id, row in self.data.items():
            parsed = self._parse_setup_id(setup_id)
            if parsed["asset"] != asset:
                continue
            if parsed["strategy"] != strategy_name:
                continue
            if parsed["regime"] != regime:
                continue

            similarity = 0
            if parsed.get("pattern", "none") == pattern:
                similarity += 1
            if parsed.get("breakout", False) == breakout:
                similarity += 1
            if parsed.get("rejection", False) == rejection:
                similarity += 1

            total = int(row.get("total", 0))
            wins = int(row.get("wins", 0))
            loss = int(row.get("loss", 0))
            winrate = (wins / total) * 100 if total > 0 else 0.0

            rows.append({
                "setup_id": setup_id,
                "similarity": similarity,
                "total": total,
                "wins": wins,
                "loss": loss,
                "winrate": round(winrate, 2),
            })

        rows.sort(key=lambda x: (x["similarity"], x["winrate"], x["total"]), reverse=True)
        return rows

    def get_adjustment(self, asset, strategy_name, indicators):
        self.refresh()
        rows = self._related_rows(asset, strategy_name, indicators)
        if not rows:
            return {
                "boost": 0.0,
                "reason": "Evolução sem histórico relacionado",
                "variant": "base"
            }

        top = rows[0]
        total = top["total"]
        winrate = top["winrate"]

        if total < 8:
            return {
                "boost": 0.0,
                "reason": "Evolução com amostra insuficiente",
                "variant": "observação"
            }

        if winrate >= 70:
            return {
                "boost": 0.24,
                "reason": f"Variação promovida ({winrate}%)",
                "variant": "promovida"
            }
        if winrate >= 60:
            return {
                "boost": 0.12,
                "reason": f"Variação favorecida ({winrate}%)",
                "variant": "favorecida"
            }
        if winrate <= 35:
            return {
                "boost": -0.18,
                "reason": f"Variação reduzida ({winrate}%)",
                "variant": "reduzida"
            }
        if winrate <= 42:
            return {
                "boost": -0.08,
                "reason": f"Variação levemente reduzida ({winrate}%)",
                "variant": "cautela"
            }

        return {
            "boost": 0.0,
            "reason": f"Variação neutra ({winrate}%)",
            "variant": "base"
        }
