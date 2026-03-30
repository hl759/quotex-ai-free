import json
import os
from storage_paths import DATA_DIR, migrate_file
from json_safe import safe_dump, safe_dumps, to_jsonable

os.makedirs(DATA_DIR, exist_ok=True)
SPECIALIST_REPUTATION_FILE = os.path.join(DATA_DIR, "alpha_hive_specialist_reputation.json")
migrate_file(SPECIALIST_REPUTATION_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_specialist_reputation.json")])


class SpecialistReputationEngine:
    def __init__(self):
        self.path = SPECIALIST_REPUTATION_FILE

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _save(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(data, f)
        os.replace(tmp, self.path)

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _empty_stats(self, specialist_id=None):
        return {
            "id": specialist_id,
            "trades": 0,
            "aligned_wins": 0,
            "aligned_losses": 0,
            "contrarian_wins": 0,
            "contrarian_losses": 0,
            "total_pnl": 0.0,
            "alignment_score": 0.0,
            "recent": [],
            "last_result": None,
        }

    def get_stats(self, specialist_id):
        data = self._load()
        return data.get(str(specialist_id), self._empty_stats(str(specialist_id)))

    def _derived(self, stats):
        trades = int(stats.get("trades", 0) or 0)
        aw = int(stats.get("aligned_wins", 0) or 0)
        al = int(stats.get("aligned_losses", 0) or 0)
        cw = int(stats.get("contrarian_wins", 0) or 0)
        cl = int(stats.get("contrarian_losses", 0) or 0)
        aligned_total = aw + al
        contrarian_total = cw + cl
        aligned_wr = round((aw / aligned_total) * 100.0, 2) if aligned_total else 0.0
        contrarian_wr = round((cw / contrarian_total) * 100.0, 2) if contrarian_total else 0.0
        recent = list(stats.get("recent", []))[:20]
        recent_score = sum(recent)
        alignment_score = float(stats.get("alignment_score", 0.0) or 0.0)
        sample_factor = min(1.0, trades / 40.0) if trades > 0 else 0.0
        reputation = 1.0 + ((alignment_score / max(1.0, trades)) * 0.18) + (recent_score / 40.0) * 0.12
        reputation = max(0.78, min(1.22, reputation))
        confidence_band = "neutra"
        if trades >= 12:
            if reputation >= 1.10:
                confidence_band = "forte"
            elif reputation <= 0.90:
                confidence_band = "fraca"
            else:
                confidence_band = "estável"
        return {
            **stats,
            "aligned_winrate": aligned_wr,
            "contrarian_winrate": contrarian_wr,
            "reputation_multiplier": round(reputation, 4),
            "sample_factor": round(sample_factor, 4),
            "confidence_band": confidence_band,
        }

    def reputation_for(self, specialist_id):
        return self._derived(self.get_stats(specialist_id))

    def register_trade(self, signal, result_data):
        participants = signal.get("council_participants") or []
        if not isinstance(participants, list) or not participants:
            return None

        outcome = str(result_data.get("result", "")).upper()
        if outcome not in ("WIN", "LOSS"):
            return None

        pnl = self._safe_float(result_data.get("gross_pnl"), 0.0)
        data = self._load()
        updated = []
        trade_signal = str(signal.get("signal", "")).upper()
        for item in participants:
            if not isinstance(item, dict):
                continue
            specialist_id = str(item.get("id", "")).strip()
            if not specialist_id:
                continue
            stats = data.get(specialist_id, self._empty_stats(specialist_id))
            stance = str(item.get("stance", "observe"))
            vote_direction = str(item.get("direction", "")).upper()
            aligned = stance == "support" and vote_direction == trade_signal
            if aligned:
                if outcome == "WIN":
                    stats["aligned_wins"] = int(stats.get("aligned_wins", 0) or 0) + 1
                    delta = 1
                else:
                    stats["aligned_losses"] = int(stats.get("aligned_losses", 0) or 0) + 1
                    delta = -1
            else:
                if outcome == "LOSS":
                    stats["contrarian_wins"] = int(stats.get("contrarian_wins", 0) or 0) + 1
                    delta = 1
                else:
                    stats["contrarian_losses"] = int(stats.get("contrarian_losses", 0) or 0) + 1
                    delta = -1

            stats["trades"] = int(stats.get("trades", 0) or 0) + 1
            stats["total_pnl"] = round(self._safe_float(stats.get("total_pnl"), 0.0) + (pnl if aligned else -pnl * 0.25), 2)
            stats["alignment_score"] = round(self._safe_float(stats.get("alignment_score"), 0.0) + delta, 4)
            recent = list(stats.get("recent", []))
            recent.insert(0, int(delta))
            stats["recent"] = recent[:20]
            stats["last_result"] = outcome
            data[specialist_id] = stats
            updated.append(self._derived(stats))

        self._save(data)
        return updated

    def snapshot(self, limit=20):
        data = self._load()
        rows = [self._derived(v) for v in data.values() if isinstance(v, dict)]
        rows.sort(
            key=lambda x: (
                x.get("reputation_multiplier", 1.0),
                x.get("aligned_winrate", 0.0),
                x.get("trades", 0),
            ),
            reverse=True,
        )
        return rows[: max(1, int(limit or 20))]