from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from alpha_hive.learning.segment_learning import segment_key
from alpha_hive.storage.state_store import get_state_store

STORE_KEY = "learning_memory_v2"
LEGACY_STORE_KEY = "learning_memory"

class LearningEngine:
    def __init__(self):
        self.store = get_state_store()
        memory = self.store.get_json(STORE_KEY, None)
        if not isinstance(memory, dict) or not memory:
            memory = self.store.get_json(LEGACY_STORE_KEY, {"assets": {}, "segments": {}})
        if not isinstance(memory, dict):
            memory = {"assets": {}, "segments": {}}
        memory.setdefault("assets", {})
        memory.setdefault("segments", {})
        self.memory = memory

    def _save(self) -> None:
        self.store.set_json(STORE_KEY, self.memory)
        self.store.set_json(LEGACY_STORE_KEY, self.memory)

    def _asset_stats(self, asset: str) -> Dict[str, int]:
        assets = self.memory.setdefault("assets", {})
        if asset not in assets:
            assets[asset] = {"wins": 0, "losses": 0}
        return assets[asset]

    def register_outcome(self, asset: str, direction: str, regime: str, specialist: str, provider: str, market_type: str, hour_bucket: str, setup_quality: str, result: str) -> None:
        asset_row = self._asset_stats(asset)
        won = str(result).upper() == "WIN"
        if won:
            asset_row["wins"] += 1
        else:
            asset_row["losses"] += 1
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        segments = self.memory.setdefault("segments", {})
        row = segments.setdefault(key, {
            "asset": asset, "direction": direction, "regime": regime, "specialist": specialist,
            "provider": provider, "market_type": market_type, "hour_bucket": hour_bucket, "setup_quality": setup_quality,
            "wins": 0, "losses": 0, "updated_at": "",
        })
        if won:
            row["wins"] += 1
        else:
            row["losses"] += 1
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def asset_boost(self, asset: str) -> float:
        row = self._asset_stats(asset)
        wins, losses = row["wins"], row["losses"]
        total = wins + losses
        if total < 20:
            return 0.0
        winrate = wins / total
        return round(max(-0.2, min(0.2, (winrate - 0.5) * 0.8)), 2)

    def segment_adjustment(self, asset: str, direction: str, regime: str, specialist: str, provider: str, market_type: str, hour_bucket: str, setup_quality: str) -> Dict[str, Any]:
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        row = self.memory.setdefault("segments", {}).get(key, {})
        wins, losses = int(row.get("wins", 0) or 0), int(row.get("losses", 0) or 0)
        total = wins + losses
        if total < 8:
            return {"score_boost": 0.0, "confidence_shift": 0, "proof_state": "building", "trades": total, "winrate": 0.0}
        winrate = wins / total
        return {
            "score_boost": round(max(-0.12, min(0.12, (winrate - 0.5) * 0.6)), 2),
            "confidence_shift": int(max(-4, min(4, round((winrate - 0.5) * 12)))),
            "proof_state": "proven_positive" if winrate >= 0.62 else "proven_negative" if winrate <= 0.42 else "building",
            "trades": total,
            "winrate": round(winrate * 100, 2),
        }

    def calibration_profile(self, asset: str) -> Dict[str, Any]:
        row = self._asset_stats(asset)
        wins, losses = row["wins"], row["losses"]
        total = wins + losses
        if total < 20:
            return {"confidence_factor": 1.0, "min_score": 2.8, "mode": "base"}
        winrate = wins / total
        return {
            "confidence_factor": 1.05 if winrate >= 0.60 else 0.93 if winrate <= 0.43 else 1.0,
            "min_score": 2.6 if winrate >= 0.60 else 3.1 if winrate <= 0.43 else 2.8,
            "mode": "confiante" if winrate >= 0.60 else "cautela" if winrate <= 0.43 else "equilibrado",
        }
