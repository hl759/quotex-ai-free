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
            memory = self.store.get_json(
                LEGACY_STORE_KEY,
                {"assets": {}, "segments": {}, "loss_causes": {}},
            )
        if not isinstance(memory, dict):
            memory = {"assets": {}, "segments": {}, "loss_causes": {}}
        memory.setdefault("assets", {})
        memory.setdefault("segments", {})
        memory.setdefault("loss_causes", {})
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
        row["reverse_would_win_count"] = round(float(row.get("reverse_would_win_count", 0.0) or 0.0) * factor, 4)
        row["counterfactual_better_count"] = round(float(row.get("counterfactual_better_count", 0.0) or 0.0) * factor, 4)
        row["late_failures"] = round(float(row.get("late_failures", 0.0) or 0.0) * factor, 4)
        row["weak_followthrough_count"] = round(float(row.get("weak_followthrough_count", 0.0) or 0.0) * factor, 4)
        row["critical_failures"] = round(float(row.get("critical_failures", 0.0) or 0.0) * factor, 4)

        cause_counts = dict(row.get("cause_counts", {}) or {})
        if cause_counts:
            row["cause_counts"] = {
                key: round(float(value or 0.0) * factor, 4)
                for key, value in cause_counts.items()
            }

    def _asset_stats(self, asset: str) -> Dict[str, Any]:
        assets = self.memory.setdefault("assets", {})
        if asset not in assets:
            assets[asset] = {"wins": 0.0, "losses": 0.0, "updated_at": ""}
        return assets[asset]

    def _merged_context(self, extra_context: Dict[str, Any] | None) -> Dict[str, Any]:
        return dict(extra_context or {})

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
        loss_cause: str = "none",
        reverse_would_win: bool = False,
        counterfactual_better: bool = False,
        entry_efficiency: str = "normal",
        operating_state: str = "OBSERVE",
        signal_type: str = "standard",
        extra_context: Dict[str, Any] | None = None,
    ) -> None:
        result_upper = str(result).upper()
        merged_context = self._merged_context(extra_context)

        asset_row = self._asset_stats(asset)
        self._apply_decay(asset_row)
        if result_upper == "WIN":
            asset_row["wins"] = float(asset_row.get("wins", 0.0) or 0.0) + 1.0
        elif result_upper == "LOSS":
            asset_row["losses"] = float(asset_row.get("losses", 0.0) or 0.0) + 1.0
        asset_row["updated_at"] = datetime.now(timezone.utc).isoformat()

        key = segment_key(
            asset,
            direction,
            regime,
            specialist,
            provider,
            market_type,
            hour_bucket,
            setup_quality,
            extra_context=merged_context,
        )
        row = self.memory.setdefault("segments", {}).setdefault(
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
                "reverse_would_win_count": 0.0,
                "counterfactual_better_count": 0.0,
                "late_failures": 0.0,
                "weak_followthrough_count": 0.0,
                "critical_failures": 0.0,
                "cause_counts": {},
                "updated_at": "",
                "operating_state": operating_state,
                "signal_type": signal_type,
            },
        )
        self._apply_decay(row)

        if result_upper == "WIN":
            row["wins"] = float(row.get("wins", 0.0) or 0.0) + 1.0
        elif result_upper == "LOSS":
            row["losses"] = float(row.get("losses", 0.0) or 0.0) + 1.0

        if reverse_would_win and result_upper == "LOSS":
            row["reverse_would_win_count"] = float(row.get("reverse_would_win_count", 0.0) or 0.0) + 1.0
        if counterfactual_better and result_upper == "LOSS":
            row["counterfactual_better_count"] = float(row.get("counterfactual_better_count", 0.0) or 0.0) + 1.0
        if entry_efficiency in ("late", "stretched") and result_upper == "LOSS":
            row["late_failures"] = float(row.get("late_failures", 0.0) or 0.0) + 1.0
        if entry_efficiency == "weak_followthrough" and result_upper == "LOSS":
            row["weak_followthrough_count"] = float(row.get("weak_followthrough_count", 0.0) or 0.0) + 1.0
        if loss_cause in (
            "wrong_direction",
            "regime_transition",
            "conflict_ignored",
            "breakout_exhaustion",
            "reversal_ignored",
        ) and result_upper == "LOSS":
            row["critical_failures"] = float(row.get("critical_failures", 0.0) or 0.0) + 1.0

        cause_counts = dict(row.get("cause_counts", {}) or {})
        if result_upper == "LOSS" and loss_cause and loss_cause != "none":
            cause_counts[loss_cause] = round(float(cause_counts.get(loss_cause, 0.0) or 0.0) + 1.0, 4)
        row["cause_counts"] = cause_counts
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
        row["operating_state"] = operating_state
        row["signal_type"] = signal_type

        cause_key = segment_key(
            asset,
            direction,
            regime,
            specialist,
            provider,
            market_type,
            hour_bucket,
            setup_quality,
            extra_context=merged_context,
        )
        cause_row = self.memory.setdefault("loss_causes", {}).setdefault(cause_key, {"counts": {}, "updated_at": ""})
        if result_upper == "LOSS" and loss_cause and loss_cause != "none":
            counts = dict(cause_row.get("counts", {}) or {})
            counts[loss_cause] = round(float(counts.get(loss_cause, 0.0) or 0.0) + 1.0, 4)
            cause_row["counts"] = counts
            cause_row["updated_at"] = datetime.now(timezone.utc).isoformat()

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
        extra_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        merged_context = self._merged_context(extra_context)
        key = segment_key(
            asset,
            direction,
            regime,
            specialist,
            provider,
            market_type,
            hour_bucket,
            setup_quality,
            extra_context=merged_context,
        )
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
                "reverse_bias": 0.0,
                "cause_pressure": 0.0,
                "cooldown_state": "none",
                "loss_cause_leader": "none",
            }

        winrate = wins / max(total, 1e-9)
        evidence = min(1.0, total / 18.0)
        reverse_hits = float(row.get("reverse_would_win_count", 0.0) or 0.0)
        late_failures = float(row.get("late_failures", 0.0) or 0.0)
        weak_followthrough_count = float(row.get("weak_followthrough_count", 0.0) or 0.0)
        critical_failures = float(row.get("critical_failures", 0.0) or 0.0)
        cause_counts = dict(row.get("cause_counts", {}) or {})

        leader = "none"
        if cause_counts:
            leader = max(cause_counts.items(), key=lambda item: item[1])[0]

        timing_failures = late_failures + weak_followthrough_count
        cause_pressure = min(
            0.28,
            ((critical_failures * 1.0) + (timing_failures * 0.55) + (reverse_hits * 0.7))
            / max(total, 1.0)
            * 0.24,
        )

        reverse_bias = 0.0
        if losses >= 3 and reverse_hits >= 2:
            reverse_bias = -round(min(0.28, (reverse_hits / max(losses, 1.0)) * 0.18), 2)

        cooldown_state = "none"
        if total >= 8 and (losses / max(total, 1.0)) >= 0.62 and (critical_failures + reverse_hits) >= 3:
            cooldown_state = "hard"
        elif total >= 6 and (losses / max(total, 1.0)) >= 0.55:
            cooldown_state = "soft"

        raw = ((winrate - 0.5) * 1.8 * evidence) + reverse_bias - cause_pressure
        score_boost = round(max(-0.30, min(0.30, raw)), 2)
        confidence_shift = int(
            max(
                -9,
                min(9, round((((winrate - 0.5) * 18 * evidence) + (reverse_bias * 10) - (cause_pressure * 18)))),
            )
        )

        if total >= 10 and winrate >= 0.60 and cause_pressure < 0.08 and reverse_hits < 1.5:
            proof_state = "proven_positive"
        elif total >= 8 and (winrate <= 0.42 or reverse_hits >= 3 or cause_pressure >= 0.12):
            proof_state = "proven_negative"
        else:
            proof_state = "building"

        return {
            "score_boost": score_boost,
            "confidence_shift": confidence_shift,
            "proof_state": proof_state,
            "trades": round(total, 2),
            "winrate": round(winrate * 100, 2),
            "reverse_bias": reverse_bias,
            "cause_pressure": round(cause_pressure, 3),
            "cooldown_state": cooldown_state,
            "loss_cause_leader": leader,
        }

    def calibration_profile(self, asset: str) -> Dict[str, Any]:
        row = self._asset_stats(asset)
        wins = float(row.get("wins", 0.0) or 0.0)
        losses = float(row.get("losses", 0.0) or 0.0)
        total = wins + losses

        if total < 18:
            return {"confidence_factor": 1.0, "min_score": 2.8, "mode": "base"}

        winrate = wins / max(total, 1.0)
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
