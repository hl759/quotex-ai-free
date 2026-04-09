from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

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

    def _parse_dt(self, value: str | None):
        if not value:
            return None
        text = str(value).strip().replace("Z", "+00:00")
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
        elapsed_days = max(0.0, (datetime.now(timezone.utc) - updated_at).total_seconds() / 86400.0)
        if elapsed_days <= 0:
            return
        factor = daily_decay ** elapsed_days
        row["wins"] = round(float(row.get("wins", 0.0) or 0.0) * factor, 4)
        row["losses"] = round(float(row.get("losses", 0.0) or 0.0) * factor, 4)

    def register_outcome(
        self,
        specialist: str,
        asset: str,
        direction: str,
        regime: str,
        provider: str,
        market_type: str,
        hour_bucket: str,
        setup_quality: str,
        result: str,
    ) -> None:
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        row = self.memory.setdefault("segments", {}).setdefault(
            key,
            {
                "specialist": specialist,
                "wins": 0.0,
                "losses": 0.0,
                "updated_at": "",
            },
        )
        self._apply_decay(row)

        result_upper = str(result).upper()
        if result_upper == "WIN":
            row["wins"] = float(row.get("wins", 0.0) or 0.0) + 1.0
        elif result_upper == "LOSS":
            row["losses"] = float(row.get("losses", 0.0) or 0.0) + 1.0

        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def weight_for(
        self,
        specialist: str,
        asset: str,
        direction: str,
        regime: str,
        provider: str,
        market_type: str,
        hour_bucket: str,
        setup_quality: str,
    ) -> float:
        key = segment_key(asset, direction, regime, specialist, provider, market_type, hour_bucket, setup_quality)
        row = self.memory.setdefault("segments", {}).get(key, {})
        wins = float(row.get("wins", 0.0) or 0.0)
        losses = float(row.get("losses", 0.0) or 0.0)
        total = wins + losses

        if total < 5:
            return 1.0

        winrate = wins / total
        evidence = min(1.0, total / 18.0)
        edge = (winrate - 0.5) * 1.2 * evidence
        return round(max(0.72, min(1.42, 1.0 + edge)), 2)

    def snapshot(self, limit: int = 25):
        rows = []
        for key, row in self.memory.setdefault("segments", {}).items():
            wins = float(row.get("wins", 0.0) or 0.0)
            losses = float(row.get("losses", 0.0) or 0.0)
            total = wins + losses
            if total <= 0:
                continue
            rows.append(
                {
                    "context": key,
                    "specialist": row.get("specialist"),
                    "wins": round(wins, 2),
                    "losses": round(losses, 2),
                    "total": round(total, 2),
                    "winrate": round((wins / total) * 100, 2),
                }
            )
        rows.sort(key=lambda item: (item["winrate"], item["total"]), reverse=True)
        return rows[:limit]
