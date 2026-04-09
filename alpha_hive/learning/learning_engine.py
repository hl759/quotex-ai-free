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

    def _parse_dt(self, value: str | None):
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _apply_decay(self, row: Dict[str, Any], daily_decay: float = 0.985) -> None:
        updated_at = self._parse_dt(str(row.get("updated_at", "") or ""))
        if not updated_at:
            return
        now = datetime.now(timezone.utc)
        elapsed_days = max(0.0, (now - updated_at).total_seconds() / 86400.0)
        if elapsed_days <= 0:
            return
        factor = daily_decay ** elapsed_days
        row["wins"] = round(float(row.get("wins", 0.0) or 0.0) * factor, 4)
        row["losses"] = round(float(row.get("losses", 0.0) or 0.0) * factor, 4)

    def _asset_stats(self, asset: str) -> Dict[str, Any]:
        assets = self.memory.setdefault("assets", {})
        if asset not in assets:
            assets[asset] = {"wins": 0.0, "losses": 0.0, "updated_at": ""}
        return assets[asset]

    def register_outcome(
        self,
        asset: str,
        direction: str,
        regime: str,
        specialist: str,
        provider: str,
        market_type: str,
        hour_bucket: str,
        setup_quality: str,
        result: str,
    ) -> None:
        result_upper = str(result).upper()

        asset_row = self._asset_stats(asset)
        self._apply_decay(asset_row)
        if result_upper == "WIN":
            asset_row["wins"] = float(asset_row.get("wins", 0.0) or 0.0) + 1.0
        elif result_upper == "LOSS":
            asset_row["losses"] = float(asset_row.get("losses", 0.0) or 0.0) + 1.0
        asset_row["updated_at"] = datetime.now(timezone.utc).isoformat()

        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        segments = self.memory.setdefault("segments", {})
        row = segments.setdefault(
            key,
            {
                "asset": asset,
                "direction": direction,
                "regime": regime,
                "specialist": specialist,
                "provider": provider,
                "market_type": market_type,
                "hour_bucket": hour_bucket,
                "setup_quality": setup_quality,
                "wins": 0.0,
                "losses": 0.0,
                "updated_at": "",
            },
        )
        self._apply_decay(row)
        if result_upper == "WIN":
            row["wins"] = float(row.get("wins", 0.0) or 0.0) + 1.0
        elif result_upper == "LOSS":
            row["losses"] = float(row.get("losses", 0.0) or 0.0) + 1.0
        row["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._save()

    def asset_boost(self, asset: str) -> float:
        row = self._asset_stats(asset)
        wins = float(row.get("wins", 0.0) or 0.0)
        losses = float(row.get("losses", 0.0) or 0.0)
        total = wins + losses
        if total < 18:
            return 0.0
        winrate = wins / total
        evidence = min(1.0, total / 40.0)
        raw = (winrate - 0.5) * 1.6 * evidence
        return round(max(-0.35, min(0.35, raw)), 2)

    def segment_adjustment(
        self,
        asset: str,
        direction: str,
        regime: str,
        specialist: str,
        provider: str,
        market_type: str,
        hour_bucket: str,
        setup_quality: str,
    ) -> Dict[str, Any]:
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        row = self.memory.setdefault("segments", {}).get(key, {})
        wins = float(row.get("wins", 0.0) or 0.0)
        losses = float(row.get("losses", 0.0) or 0.0)
        total = wins + losses

        if total < 6:
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "proof_state": "building",
                "trades": round(total, 2),
                "winrate": 0.0,
            }

        winrate = wins / total
        evidence = min(1.0, total / 18.0)
        raw = (winrate - 0.5) * 1.8 * evidence
        score_boost = round(max(-0.25, min(0.25, raw)), 2)
        confidence_shift = int(max(-8, min(8, round((winrate - 0.5) * 18 * evidence))))

        if total >= 10 and winrate >= 0.60:
            proof_state = "proven_positive"
        elif total >= 10 and winrate <= 0.42:
            proof_state = "proven_negative"
        else:
            proof_state = "building"

        return {
            "score_boost": score_boost,
            "confidence_shift": confidence_shift,
            "proof_state": proof_state,
            "trades": round(total, 2),
            "winrate": round(winrate * 100, 2),
        }

    def calibration_profile(self, asset: str) -> Dict[str, Any]:
        row = self._asset_stats(asset)
        wins = float(row.get("wins", 0.0) or 0.0)
        losses = float(row.get("losses", 0.0) or 0.0)
        total = wins + losses

        if total < 18:
            return {"confidence_factor": 1.0, "min_score": 2.8, "mode": "base"}

        winrate = wins / total
        evidence = min(1.0, total / 60.0)

        confidence_factor = 1.0 + max(-0.10, min(0.10, (winrate - 0.5) * 0.24 * evidence))
        min_score = 2.8 - max(-0.35, min(0.35, (winrate - 0.5) * 1.2 * evidence))

        if winrate >= 0.60:
            mode = "confiante"
        elif winrate <= 0.43:
            mode = "cautela"
        else:
            mode = "equilibrado"

        return {
            "confidence_factor": round(confidence_factor, 3),
            "min_score": round(min_score, 2),
            "mode": mode,
        }
