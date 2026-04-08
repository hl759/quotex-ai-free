from __future__ import annotations

import math
from typing import Dict, List

import pandas as pd

from alpha_hive.core.contracts import Candle

class IndicatorEngine:
    def _rsi_series(self, series, period: int = 14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, 1e-9)
        return 100 - (100 / (1 + rs))

    def _aggregate_to_m5(self, df: pd.DataFrame):
        if len(df) < 5:
            return None
        tmp = df.copy()
        tmp["grp"] = list(range(len(tmp)))[::-1]
        tmp["grp"] = tmp["grp"] // 5
        agg = tmp.groupby("grp", sort=False).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        agg = agg.iloc[::-1].reset_index(drop=True)
        if len(agg) < 3:
            return None
        return agg

    def _detect_pattern(self, df: pd.DataFrame):
        if len(df) < 2:
            return None
        last = df.iloc[-1]
        prev = df.iloc[-2]
        bullish = last["close"] > last["open"] and prev["close"] < prev["open"] and last["close"] > prev["open"]
        bearish = last["close"] < last["open"] and prev["close"] > prev["open"] and last["close"] < prev["open"]
        if bullish:
            return "bullish"
        if bearish:
            return "bearish"
        return None

    def _regime(self, df: pd.DataFrame) -> str:
        if len(df) < 20:
            return "unknown"
        close = df["close"]
        returns = close.pct_change().dropna()
        std = returns.std()
        slope = close.iloc[-1] - close.iloc[-10]
        range_recent = (df["high"].tail(10).max() - df["low"].tail(10).min()) / max(close.iloc[-1], 1e-9)
        if std > 0.006:
            return "chaotic"
        if abs(slope) > close.iloc[-1] * 0.004 and range_recent > 0.003:
            return "trend"
        if range_recent < 0.0025:
            return "sideways"
        return "mixed"

    def _breakout_quality(self, df: pd.DataFrame):
        if len(df) < 6:
            return False, "absent"
        prev_high = df["high"].iloc[-6:-1].max()
        prev_low = df["low"].iloc[-6:-1].min()
        last = df.iloc[-1]
        candle_range = max(last["high"] - last["low"], 1e-9)
        body = abs(last["close"] - last["open"])
        body_ratio = body / candle_range
        close_position = (last["close"] - last["low"]) / candle_range
        recent_moves = (df["close"].tail(6) - df["open"].tail(6)).abs() / df["close"].tail(6).replace(0, 1e-9)
        move_now = abs(last["close"] - last["open"]) / max(last["close"], 1e-9)
        recent_mean_move = float(recent_moves.iloc[:-1].mean()) if len(recent_moves) > 1 else move_now
        expansion_ratio = move_now / max(recent_mean_move, 1e-9)
        broke_up = last["close"] > prev_high
        broke_down = last["close"] < prev_low
        breakout = bool(broke_up or broke_down)
        if not breakout:
            return False, "absent"
        directional_close = close_position >= 0.72 if broke_up else close_position <= 0.28
        if body_ratio >= 0.58 and directional_close and expansion_ratio >= 1.18:
            return True, "strong"
        return True, "weak"

    def _rejection_quality(self, df: pd.DataFrame):
        if len(df) < 2:
            return False, "absent"
        last = df.iloc[-1]
        candle_range = max(last["high"] - last["low"], 1e-9)
        body = abs(last["close"] - last["open"])
        body_ratio = body / candle_range
        upper_wick = last["high"] - max(last["open"], last["close"])
        lower_wick = min(last["open"], last["close"]) - last["low"]
        upper_ratio = upper_wick / candle_range
        lower_ratio = lower_wick / candle_range
        close_position = (last["close"] - last["low"]) / candle_range
        strong_upper = upper_ratio > 0.52 and body_ratio < 0.42 and close_position < 0.42
        strong_lower = lower_ratio > 0.52 and body_ratio < 0.42 and close_position > 0.58
        weak_upper = upper_ratio > 0.42
        weak_lower = lower_ratio > 0.42
        if strong_upper or strong_lower:
            return True, "strong"
        if weak_upper or weak_lower:
            return True, "weak"
        return False, "absent"

    def calculate(self, candles: List[Candle]) -> Dict[str, object]:
        df = pd.DataFrame([c.to_dict() for c in candles])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df["ema9"] = df["close"].ewm(span=9).mean()
        df["ema21"] = df["close"].ewm(span=21).mean()
        df["ema50"] = df["close"].ewm(span=50).mean()
        trend_m1 = "bull" if df["ema9"].iloc[-1] > df["ema21"].iloc[-1] else "bear"
        rsi = self._rsi_series(df["close"]).iloc[-1]
        pattern = self._detect_pattern(df)
        volatility = bool(df["close"].pct_change().tail(10).std() > 0.0012)
        regime = self._regime(df)
        breakout, breakout_quality = self._breakout_quality(df)
        rejection, rejection_quality = self._rejection_quality(df)
        last = df.iloc[-1]
        candle_range = max(last["high"] - last["low"], 1e-9)
        body = abs(last["close"] - last["open"])
        body_ratio = body / candle_range
        close_position = (last["close"] - last["low"]) / candle_range
        candle_move = body / max(last["close"], 1e-9)
        recent_moves = (df["close"].tail(8) - df["open"].tail(8)).abs() / df["close"].tail(8).replace(0, 1e-9)
        baseline_move = float(recent_moves.iloc[:-1].mean()) if len(recent_moves) > 1 else candle_move
        expansion_ratio = candle_move / max(baseline_move, 1e-9)
        moved_too_fast = candle_move > 0.0022 or (body_ratio > 0.68 and expansion_ratio > 1.5)
        explosive_expansion = candle_move > 0.0034 or expansion_ratio > 1.9
        late_entry_risk = moved_too_fast and ((trend_m1 == "bull" and close_position > 0.78) or (trend_m1 == "bear" and close_position < 0.22))
        recent_range = (df["high"].tail(8).max() - df["low"].tail(8).min()) / max(df["close"].iloc[-1], 1e-9)
        is_sideways = recent_range < 0.0022
        m5 = self._aggregate_to_m5(df)
        trend_m5 = "neutral"
        if m5 is not None:
            m5["ema9"] = m5["close"].ewm(span=9).mean()
            m5["ema21"] = m5["close"].ewm(span=21).mean()
            trend_m5 = "bull" if m5["ema9"].iloc[-1] > m5["ema21"].iloc[-1] else "bear"
        ema_spread = abs(df["ema9"].iloc[-1] - df["ema21"].iloc[-1]) / max(df["close"].iloc[-1], 1e-9)
        if trend_m5 == trend_m1 and ema_spread >= 0.0010:
            trend_quality_signal = "forte"
        elif trend_m5 == trend_m1 and ema_spread >= 0.00045:
            trend_quality_signal = "aceitavel"
        else:
            trend_quality_signal = "fragil"
        return {
            "trend_m1": trend_m1,
            "trend_m5": trend_m5,
            "rsi": float(rsi) if not math.isnan(rsi) else 50.0,
            "pattern": pattern,
            "volatility": volatility,
            "regime": regime,
            "breakout": breakout,
            "breakout_quality": breakout_quality,
            "rejection": rejection,
            "rejection_quality": rejection_quality,
            "trend_quality_signal": trend_quality_signal,
            "moved_too_fast": moved_too_fast,
            "late_entry_risk": late_entry_risk,
            "explosive_expansion": explosive_expansion,
            "is_sideways": is_sideways,
        }
