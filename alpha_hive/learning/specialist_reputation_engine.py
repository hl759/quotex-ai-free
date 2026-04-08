from __future__ import annotations

from datetime import datetime, timezone

from alpha_hive.learning.segment_learning import segment_key
from alpha_hive.storage.state_store import get_state_store

STORE_KEY = "specialist_reputation_v2"
LEGACY_STORE_KEY = "specialist_reputation"

class SpecialistReputationEngine:
    def __init__(self):
        self.store = get_state_store()
        memory = self.store.get_json(STORE_KEY, None)
        if not isinstance(memory, dict) or not memory:
            memory = self.store.get_json(LEGACY_STORE_KEY, {"segments": {}})
        if not isinstance(memory, dict):
            memory = {"segments": {}}
        memory.setdefault("segments", {})
        self.memory = memory

    def _save(self) -> None:
        self.store.set_json(STORE_KEY, self.memory)
        self.store.set_json(LEGACY_STORE_KEY, self.memory)

    def register_outcome(self, specialist: str, asset: str, direction: str, regime: str, provider: str, market_type: str, hour_bucket: str, setup_quality: str, result: str) -> None:
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        row = self.memory.setdefault("segments", {}).setdefault(key, {
            "specialist": specialist,
            "wins": 0,
            "losses": 0,
            "updated_at": "",
        })
        if str(result).upper() == "WIN":
            row["wins"] += 1
        else:
            row["losses"] += 1
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def weight_for(self, specialist: str, asset: str, direction: str, regime: str, provider: str, market_type: str, hour_bucket: str, setup_quality: str) -> float:
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        row = self.memory.setdefault("segments", {}).get(key, {})
        wins = int(row.get("wins", 0) or 0)
        losses = int(row.get("losses", 0) or 0)
        total = wins + losses
        if total < 6:
            return 1.0
        winrate = wins / total
        return round(max(0.75, min(1.35, 1.0 + ((winrate - 0.5) * 0.8))), 2)

    def snapshot(self, limit: int = 25):
        rows = []
        for key, row in self.memory.setdefault("segments", {}).items():
            wins = int(row.get("wins", 0) or 0)
            losses = int(row.get("losses", 0) or 0)
            total = wins + losses
            if total <= 0:
                continue
            rows.append({
                "context": key,
                "specialist": row.get("specialist"),
                "wins": wins,
                "losses": losses,
                "total": total,
                "winrate": round((wins / total) * 100, 2),
            })
        rows.sort(key=lambda item: (item["winrate"], item["total"]), reverse=True)
        return rows[:limit]
