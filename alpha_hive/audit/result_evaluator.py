from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import Candle, FinalDecision, TradeOutcome
from alpha_hive.core.ids import new_uid


class ResultEvaluator:
    def _extract_close(self, candle: Candle) -> float:
        return float(candle.close)

    def _safe_feature(self, features: Dict[str, Any], key: str, default: Any = None) -> Any:
        value = features.get(key, default)
        return default if value is None else value

    def _binary_result(self, direction: str, entry_price: float, exit_price: float) -> str:
        if direction == "CALL":
            return "WIN" if exit_price > entry_price else "LOSS" if exit_price < entry_price else "DRAW"
        return "WIN" if exit_price < entry_price else "LOSS" if exit_price > entry_price else "DRAW"

    def _adverse_excursion(self, direction: str, entry_price: float, candle: Candle) -> float:
        base = max(abs(entry_price), 1e-9)
        if direction == "CALL":
            return round(max(0.0, (entry_price - float(candle.low)) / base), 6)
        return round(max(0.0, (float(candle.high) - entry_price) / base), 6)

    def _favorable_excursion(self, direction: str, entry_price: float, candle: Candle) -> float:
        base = max(abs(entry_price), 1e-9)
        if direction == "CALL":
            return round(max(0.0, (float(candle.high) - entry_price) / base), 6)
        return round(max(0.0, (entry_price - float(candle.low)) / base), 6)

    def _classify_loss(
        self,
        features: Dict[str, Any],
        consensus_strength: float,
        reverse_would_win: bool,
        weak_followthrough: bool,
        regime_shift_detected: bool,
        overextension_detected: bool,
    ) -> str:
        if float(features.get("data_quality_score", 1.0) or 1.0) < 0.55:
            return "data_quality_failure"
        if reverse_would_win and str(features.get("trend_m1", "")) != str(features.get("trend_m5", "")):
            return "conflict_ignored"
        if reverse_would_win and bool(features.get("rejection", False)) and not bool(features.get("breakout", False)):
            return "reversal_ignored"
        if reverse_would_win:
            return "wrong_direction"
        if bool(features.get("breakout", False)) and (
            str(features.get("breakout_quality", "")) == "strong" or overextension_detected
        ):
            return "breakout_exhaustion"
        if overextension_detected:
            return "overextended_move"
        if bool(features.get("late_entry_risk", False)):
            return "late_entry"
        if bool(features.get("volatility", False)):
            return "volatility_trap"
        if regime_shift_detected:
            return "regime_transition"
        if bool(features.get("is_sideways", False)):
            return "sideways_noise"
        if consensus_strength < 0.56:
            return "weak_consensus_failure"
        if weak_followthrough:
            return "followthrough_failure"
        return "timing_degradation"

    def _to_ts(self, value: Any) -> Optional[float]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            val = float(value)
            return val if val > 0 else None

        text = str(value).strip()
        if not text:
            return None

        try:
            if text.isdigit():
                val = float(text)
                return val if val > 0 else None
        except Exception:
            pass

        try:
            val = float(text)
            return val if val > 0 else None
        except Exception:
            pass

        for candidate in (
            text.replace("Z", "+00:00"),
            text.replace(" UTC", "+00:00"),
            text,
        ):
            try:
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).timestamp()
            except Exception:
                continue

        return None

    def _indexed_candles(self, candles: List[Candle]) -> List[Tuple[int, Candle, float]]:
        indexed: List[Tuple[int, Candle, float]] = []
        for idx, candle in enumerate(candles):
            ts = self._to_ts(getattr(candle, "ts", None))
            if ts is None:
                continue
            indexed.append((idx, candle, ts))
        indexed.sort(key=lambda item: item[2])
        return indexed

    def _first_at_or_after(self, indexed: List[Tuple[int, Candle, float]], target_ts: float) -> Optional[Tuple[int, Candle, float]]:
        for item in indexed:
            if item[2] >= target_ts:
                return item
        return None

    def _last_at_or_before(self, indexed: List[Tuple[int, Candle, float]], target_ts: float) -> Optional[Tuple[int, Candle, float]]:
        found = None
        for item in indexed:
            if item[2] <= target_ts:
                found = item
            else:
                break
        return found

    def _resolve_entry_exit(
        self,
        candles: List[Candle],
        entry_ts: Optional[float],
        expiration_ts: Optional[float],
    ) -> Tuple[Optional[Candle], Optional[Candle], Optional[float], Optional[float], str]:
        if len(candles) < 2:
            return None, None, None, None, "insufficient"

        indexed = self._indexed_candles(candles)
        if len(indexed) < 2 or entry_ts is None or expiration_ts is None:
            entry = candles[-2]
            exit_ = candles[-1]
            return (
                entry,
                exit_,
                self._to_ts(entry.ts),
                self._to_ts(exit_.ts),
                "fallback_tail",
            )

        entry_item = self._first_at_or_after(indexed, entry_ts) or self._last_at_or_before(indexed, entry_ts)
        exit_item = self._first_at_or_after(indexed, expiration_ts) or self._last_at_or_before(indexed, expiration_ts)

        if entry_item is None or exit_item is None:
            entry = candles[-2]
            exit_ = candles[-1]
            return (
                entry,
                exit_,
                self._to_ts(entry.ts),
                self._to_ts(exit_.ts),
                "fallback_tail",
            )

        entry_idx, entry_candle, entry_candle_ts = entry_item
        exit_idx, exit_candle, exit_candle_ts = exit_item

        if exit_idx <= entry_idx:
            for idx, candle, candle_ts in indexed:
                if idx > entry_idx:
                    exit_idx, exit_candle, exit_candle_ts = idx, candle, candle_ts
                    break

        if exit_idx <= entry_idx:
            return None, None, None, None, "waiting_next_candle"

        exact_entry = abs(entry_candle_ts - entry_ts) <= 3
        exact_exit = abs(exit_candle_ts - expiration_ts) <= 3
        mode = "timestamp_exact" if exact_entry and exact_exit else "timestamp_approx"
        return entry_candle, exit_candle, entry_candle_ts, exit_candle_ts, mode

    def evaluate(
        self,
        decision: FinalDecision,
        candles: List[Candle],
        delay_seconds: int = 0,
        payout: Optional[float] = None,
        analysis_ts: Optional[float] = None,
        entry_ts: Optional[float] = None,
        expiration_ts: Optional[float] = None,
    ) -> TradeOutcome | None:
        if decision.direction not in ("CALL", "PUT") or len(candles) < 2:
            return None

        payout = float(payout if payout is not None else SETTINGS.default_payout)
        features = dict(decision.features or {})

        signal_analysis_ts = self._to_ts(analysis_ts)
        signal_entry_ts = self._to_ts(entry_ts)
        signal_expiration_ts = self._to_ts(expiration_ts)

        entry, exit_, entry_candle_ts, exit_candle_ts, resolution_mode = self._resolve_entry_exit(
            candles,
            signal_entry_ts,
            signal_expiration_ts,
        )
        if entry is None or exit_ is None:
            return None

        entry_price = self._extract_close(entry)
        exit_price = self._extract_close(exit_)
        result = self._binary_result(str(decision.direction), entry_price, exit_price)

        reverse_direction = "PUT" if str(decision.direction) == "CALL" else "CALL"
        reverse_result = self._binary_result(reverse_direction, entry_price, exit_price)
        reverse_would_win = result == "LOSS" and reverse_result == "WIN"
        counterfactual_better = reverse_would_win

        stake = max(0.0, float(decision.suggested_stake or 0.0))
        if result == "WIN":
            gross_pnl = round(stake * payout, 2)
            gross_r = round(payout, 4)
        elif result == "LOSS":
            gross_pnl = round(-stake, 2)
            gross_r = -1.0
        else:
            gross_pnl = 0.0
            gross_r = 0.0

        prev_close = float(getattr(entry, "open", entry_price))
        indexed = self._indexed_candles(candles)
        if indexed:
            current_idx = next((i for i, (_, _, ts) in enumerate(indexed) if ts == entry_candle_ts), None)
            if current_idx is not None and current_idx > 0:
                prev_close = float(indexed[current_idx - 1][1].close)

        pre_move = abs(entry_price - prev_close) / max(abs(prev_close), 1e-9)
        exit_range = max(abs(float(exit_.high) - float(exit_.low)), 1e-9)
        body_to_range = abs(exit_price - entry_price) / exit_range
        body_move = abs(exit_price - entry_price) / max(abs(entry_price), 1e-9)

        weak_followthrough = body_to_range < 0.25 or body_move < 0.00012
        regime = str(self._safe_feature(features, "regime", "unknown"))
        trend_m1 = str(self._safe_feature(features, "trend_m1", "unknown"))
        trend_m5 = str(self._safe_feature(features, "trend_m5", "unknown"))
        regime_shift_detected = trend_m1 != trend_m5 or regime in ("mixed", "transition")
        overextension_detected = bool(self._safe_feature(features, "moved_too_fast", False)) or bool(
            self._safe_feature(features, "explosive_expansion", False)
        ) or pre_move > 0.0012

        if bool(self._safe_feature(features, "late_entry_risk", False)) or bool(self._safe_feature(features, "moved_too_fast", False)):
            entry_efficiency = "late"
            timing_failure_mode = "late_entry"
        elif overextension_detected:
            entry_efficiency = "stretched"
            timing_failure_mode = "stretched_move"
        elif weak_followthrough:
            entry_efficiency = "weak_followthrough"
            timing_failure_mode = "weak_followthrough"
        else:
            entry_efficiency = "good" if result == "WIN" else "normal"
            timing_failure_mode = "none"

        followthrough_quality = "weak" if weak_followthrough else "strong" if result == "WIN" and body_to_range >= 0.60 else "normal"
        loss_cause = "none"
        if result == "LOSS":
            loss_cause = self._classify_loss(
                features=features,
                consensus_strength=float(decision.council.get("consensus_strength", 0.0) if decision.council else 0.0),
                reverse_would_win=reverse_would_win,
                weak_followthrough=weak_followthrough,
                regime_shift_detected=regime_shift_detected,
                overextension_detected=overextension_detected,
            )

        timing_quality = "late" if entry_efficiency in ("late", "stretched") else "normal"
        if weak_followthrough and timing_quality == "normal":
            timing_quality = "fragile"

        mae = self._adverse_excursion(str(decision.direction), entry_price, exit_)
        mfe = self._favorable_excursion(str(decision.direction), entry_price, exit_)

        return TradeOutcome(
            uid=new_uid("trade"),
            asset=decision.asset,
            direction=str(decision.direction),
            result=result,
            entry_price=entry_price,
            exit_price=exit_price,
            payout=payout,
            stake=stake,
            gross_pnl=gross_pnl,
            gross_r=gross_r,
            evaluation_mode=f"candle_close_enriched:{resolution_mode}",
            provider=decision.provider,
            state=decision.state,
            consensus_strength=float(decision.council.get("consensus_strength", 0.0) if decision.council else 0.0),
            timing_quality=timing_quality,
            delay_seconds=delay_seconds,
            loss_cause=loss_cause,
            reverse_would_win=reverse_would_win,
            reverse_direction=reverse_direction,
            reverse_result=reverse_result,
            counterfactual_better=counterfactual_better,
            entry_efficiency=entry_efficiency,
            followthrough_quality=followthrough_quality,
            weak_followthrough=weak_followthrough,
            regime_shift_detected=regime_shift_detected,
            overextension_detected=overextension_detected,
            timing_failure_mode=timing_failure_mode,
            mae=mae,
            mfe=mfe,
            signal_analysis_ts=signal_analysis_ts,
            signal_entry_ts=signal_entry_ts,
            signal_expiration_ts=signal_expiration_ts,
            entry_candle_ts=entry_candle_ts,
            exit_candle_ts=exit_candle_ts,
            evaluated_at_ts=datetime.now(timezone.utc).timestamp(),
        )
