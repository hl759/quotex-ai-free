from __future__ import annotations

from typing import Dict, List

import pandas as pd

from alpha_hive.core.contracts import Candle


class RegimeTransitionEngine:
    def _frame(self, candles: List[Candle]) -> pd.DataFrame:
        df = pd.DataFrame([c.to_dict() for c in candles])
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = df[col].astype(float)
        return df

    def assess(self, candles_m1: List[Candle], candles_m5: List[Candle], base: Dict[str, object]) -> Dict[str, object]:
        if len(candles_m1) < 12:
            return {
                "regime_transition_state": "stable",
                "trend_persistence": 0.5,
                "exhaustion_risk": 0.0,
                "fake_move_risk": 0.0,
                "compression_state": "normal",
                "followthrough_bias": 0.0,
            }

        df1 = self._frame(candles_m1)
        df5 = self._frame(candles_m5) if candles_m5 else df1.iloc[-10:].copy()

        df1["ema9"] = df1["close"].ewm(span=9).mean()
        df1["ema21"] = df1["close"].ewm(span=21).mean()
        df5["ema9"] = df5["close"].ewm(span=9).mean()
        df5["ema21"] = df5["close"].ewm(span=21).mean()

        m1_spread = abs(df1["ema9"].iloc[-1] - df1["ema21"].iloc[-1]) / max(df1["close"].iloc[-1], 1e-9)
        m5_spread = abs(df5["ema9"].iloc[-1] - df5["ema21"].iloc[-1]) / max(df5["close"].iloc[-1], 1e-9)

        trend_m1 = str(base.get("trend_m1", "unknown"))
        trend_m5 = str(base.get("trend_m5", "unknown"))

        returns = df1["close"].pct_change().dropna()
        recent_std = float(returns.tail(8).std()) if not returns.empty else 0.0

        recent_range = (df1["high"].tail(8).max() - df1["low"].tail(8).min()) / max(df1["close"].iloc[-1], 1e-9)
        older_range = (df1["high"].tail(16).head(8).max() - df1["low"].tail(16).head(8).min()) / max(df1["close"].iloc[-1], 1e-9) if len(df1) >= 16 else recent_range

        last = df1.iloc[-1]
        candle_range = max(last["high"] - last["low"], 1e-9)
        body_ratio = abs(last["close"] - last["open"]) / candle_range
        close_position = (last["close"] - last["low"]) / candle_range

        moved_too_fast = bool(base.get("moved_too_fast", False))
        explosive = bool(base.get("explosive_expansion", False))
        breakout = bool(base.get("breakout", False))
        rejection = bool(base.get("rejection", False))
        sideways = bool(base.get("is_sideways", False))
        late_entry_risk = bool(base.get("late_entry_risk", False))

        trend_persistence = 0.45
        if trend_m1 == trend_m5 and trend_m1 in ("bull", "bear"):
            trend_persistence = min(0.98, 0.55 + (m1_spread * 180) + (m5_spread * 240))
        elif trend_m1 != trend_m5:
            trend_persistence = max(0.08, 0.32 - (m1_spread * 45))
        trend_persistence = round(float(max(0.0, min(1.0, trend_persistence))), 3)

        compression_state = "normal"
        if recent_range < 0.0018 and older_range > recent_range * 1.18:
            compression_state = "tight"
        elif recent_range > older_range * 1.45:
            compression_state = "expanding"

        exhaustion_risk = 0.0
        exhaustion_risk += 0.34 if moved_too_fast else 0.0
        exhaustion_risk += 0.28 if explosive else 0.0
        exhaustion_risk += 0.22 if late_entry_risk else 0.0
        exhaustion_risk += 0.14 if breakout and str(base.get("breakout_quality", "")) == "strong" else 0.0
        exhaustion_risk += 0.12 if body_ratio > 0.72 else 0.0
        exhaustion_risk = round(min(1.0, exhaustion_risk), 3)

        fake_move_risk = 0.0
        fake_move_risk += 0.30 if trend_m1 != trend_m5 else 0.0
        fake_move_risk += 0.24 if rejection and breakout else 0.0
        fake_move_risk += 0.18 if sideways else 0.0
        fake_move_risk += 0.14 if recent_std > 0.0016 else 0.0
        if breakout and body_ratio < 0.44:
            fake_move_risk += 0.16
        fake_move_risk = round(min(1.0, fake_move_risk), 3)

        followthrough_bias = 0.0
        if trend_m1 == trend_m5 and trend_m1 in ("bull", "bear"):
            followthrough_bias += 0.22
        if breakout and str(base.get("breakout_quality", "")) == "strong":
            followthrough_bias += 0.15
        if rejection and sideways:
            followthrough_bias -= 0.08
        if close_position > 0.72 or close_position < 0.28:
            followthrough_bias += 0.05
        if late_entry_risk or moved_too_fast:
            followthrough_bias -= 0.18
        if fake_move_risk > 0.45:
            followthrough_bias -= 0.16
        followthrough_bias = round(max(-1.0, min(1.0, followthrough_bias)), 3)

        transition_state = "stable"
        if trend_m1 != trend_m5 and (breakout or rejection):
            transition_state = "transition"
        elif exhaustion_risk >= 0.62:
            transition_state = "exhaustion"
        elif compression_state == "tight" and breakout:
            transition_state = "release"
        elif sideways and trend_m1 != trend_m5:
            transition_state = "pre_transition"

        return {
            "regime_transition_state": transition_state,
            "trend_persistence": trend_persistence,
            "exhaustion_risk": exhaustion_risk,
            "fake_move_risk": fake_move_risk,
            "compression_state": compression_state,
            "followthrough_bias": followthrough_bias,
        }
