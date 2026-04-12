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

        merit_counts = dict(row.get("merit_counts", {}) or {})
        if merit_counts:
            row["merit_counts"] = {
                key: round(float(value or 0.0) * factor, 4)
                for key, value in merit_counts.items()
            }

    def _rate(self, merit_counts: Dict[str, Any], name: str, total: float) -> float:
        return float(merit_counts.get(name, 0.0) or 0.0) / max(total, 1.0)

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
        weight: float = 1.0,
        merit_mode: str = "standard",
        extra_context: Dict[str, Any] | None = None,
    ) -> None:
        key = segment_key(
            asset,
            direction,
            regime,
            specialist,
            provider,
            market_type,
            hour_bucket,
            setup_quality,
            extra_context=extra_context,
        )
        row = self.memory.setdefault("segments", {}).setdefault(
            key,
            {
                "specialist": specialist,
                "wins": 0.0,
                "losses": 0.0,
                "merit_counts": {},
                "updated_at": "",
            },
        )
        self._apply_decay(row)

        safe_weight = max(0.2, min(1.3, float(weight or 1.0)))
        result_upper = str(result).upper()

        if result_upper == "WIN":
            row["wins"] = float(row.get("wins", 0.0) or 0.0) + safe_weight
        elif result_upper == "LOSS":
            row["losses"] = float(row.get("losses", 0.0) or 0.0) + safe_weight

        merit_counts = dict(row.get("merit_counts", {}) or {})
        merit_counts[merit_mode] = round(float(merit_counts.get(merit_mode, 0.0) or 0.0) + safe_weight, 4)
        row["merit_counts"] = merit_counts
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
        extra_context: Dict[str, Any] | None = None,
    ) -> float:
        key = segment_key(
            asset,
            direction,
            regime,
            specialist,
            provider,
            market_type,
            hour_bucket,
            setup_quality,
            extra_context=extra_context,
        )
        row = self.memory.setdefault("segments", {}).get(key, {})
        wins = float(row.get("wins", 0.0) or 0.0)
        losses = float(row.get("losses", 0.0) or 0.0)
        total = wins + losses

        if total < 4:
            return 1.0

        winrate = wins / max(total, 1e-9)
        evidence = min(1.0, total / 18.0)
        merit_counts = dict(row.get("merit_counts", {}) or {})

        bonus = 0.0
        bonus += min(0.12, self._rate(merit_counts, "correct_veto", total) * 0.18)
        bonus += min(0.08, self._rate(merit_counts, "counterfactual_correct_direction", total) * 0.12)
        bonus += min(0.06, self._rate(merit_counts, "good_trend_reading", total) * 0.10)
        bonus += min(0.06, self._rate(merit_counts, "good_sideways_reading", total) * 0.10)
        bonus += min(0.06, self._rate(merit_counts, "aligned_good_consensus", total) * 0.08)
        bonus += min(0.05, self._rate(merit_counts, "high_quality_contribution", total) * 0.08)

        penalty = 0.0
        penalty += min(0.14, self._rate(merit_counts, "wrong_direction", total) * 0.18)
        penalty += min(0.10, self._rate(merit_counts, "conflict_ignored", total) * 0.16)
        penalty += min(0.10, self._rate(merit_counts, "breakout_chase_failure", total) * 0.14)
        penalty += min(0.08, self._rate(merit_counts, "reversal_without_proof", total) * 0.12)
        penalty += min(0.08, self._rate(merit_counts, "regime_transition_misread", total) * 0.12)
        penalty += min(0.07, self._rate(merit_counts, "aligned_bad_consensus", total) * 0.11)
        penalty += min(0.06, self._rate(merit_counts, "unnecessary_veto", total) * 0.10)
        penalty += min(0.05, self._rate(merit_counts, "structurally_fragile_contribution", total) * 0.08)
        penalty += min(0.04, self._rate(merit_counts, "correct_direction_bad_timing", total) * 0.05)

        edge = (winrate - 0.5) * 1.25 * evidence
        edge += bonus
        edge -= penalty
        return round(max(0.62, min(1.58, 1.0 + edge)), 2)

    def snapshot(self, limit: int = 25):
        rows = []
        for key, row in self.memory.setdefault("segments", {}).items():
            wins = float(row.get("wins", 0.0) or 0.0)
            losses = float(row.get("losses", 0.0) or 0.0)
            total = wins + losses
            if total <= 0:
                continue

            merit_counts = dict(row.get("merit_counts", {}) or {})
            merit_top = sorted(
                merit_counts.items(),
                key=lambda item: float(item[1] or 0.0),
                reverse=True,
            )[:4]

            rows.append(
                {
                    "context": key,
                    "specialist": row.get("specialist"),
                    "wins": round(wins, 2),
                    "losses": round(losses, 2),
                    "total": round(total, 2),
                    "winrate": round((wins / max(total, 1.0)) * 100, 2),
                    "top_merits": merit_top,
                }
            )
        rows.sort(key=lambda item: (item["winrate"], item["total"]), reverse=True)
        return rows[:limit]
