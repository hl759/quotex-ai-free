from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pandas as pd

from alpha_hive.core.contracts import Candle


class IndicatorEngine:

    # ── Helpers existentes ────────────────────────────────────────────────

    def _rsi_series(self, series: pd.Series, period: int = 14) -> pd.Series:
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
        agg = tmp.groupby("grp", sort=False).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        )
        agg = agg.iloc[::-1].reset_index(drop=True)
        if len(agg) < 3:
            return None
        return agg

    def _detect_pattern(self, df: pd.DataFrame):
        """Padrão engolfante de 2 candles — mantido para compatibilidade."""
        if len(df) < 2:
            return None
        last = df.iloc[-1]
        prev = df.iloc[-2]
        bullish = (
            last["close"] > last["open"]
            and prev["close"] < prev["open"]
            and last["close"] > prev["open"]
        )
        bearish = (
            last["close"] < last["open"]
            and prev["close"] > prev["open"]
            and last["close"] < prev["open"]
        )
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
        range_recent = (
            (df["high"].tail(10).max() - df["low"].tail(10).min())
            / max(close.iloc[-1], 1e-9)
        )
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
        recent_moves = (
            (df["close"].tail(6) - df["open"].tail(6)).abs()
            / df["close"].tail(6).replace(0, 1e-9)
        )
        move_now = abs(last["close"] - last["open"]) / max(last["close"], 1e-9)
        recent_mean_move = (
            float(recent_moves.iloc[:-1].mean()) if len(recent_moves) > 1 else move_now
        )
        expansion_ratio = move_now / max(recent_mean_move, 1e-9)
        broke_up = last["close"] > prev_high
        broke_down = last["close"] < prev_low
        breakout = bool(broke_up or broke_down)
        if not breakout:
            return False, "absent"
        directional_close = (
            close_position >= 0.72 if broke_up else close_position <= 0.28
        )
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

    # ── Novos helpers: análise avançada ──────────────────────────────────

    def _atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range."""
        high = df["high"]
        low = df["low"]
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        return tr.rolling(period, min_periods=max(1, period // 2)).mean()

    def _swing_points(
        self, df: pd.DataFrame, bars: int = 3
    ) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
        """Detecta swing highs e swing lows usando look-around de N barras."""
        n = len(df)
        if n < bars * 2 + 1:
            return [], []
        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []
        for i in range(bars, n - bars):
            h = float(df["high"].iloc[i])
            lo = float(df["low"].iloc[i])
            if all(h >= float(df["high"].iloc[i - j]) for j in range(1, bars + 1)) and all(
                h >= float(df["high"].iloc[i + j]) for j in range(1, bars + 1)
            ):
                swing_highs.append((i, h))
            if all(lo <= float(df["low"].iloc[i - j]) for j in range(1, bars + 1)) and all(
                lo <= float(df["low"].iloc[i + j]) for j in range(1, bars + 1)
            ):
                swing_lows.append((i, lo))
        return swing_highs, swing_lows

    def _fvg(
        self, df: pd.DataFrame
    ) -> Tuple[bool, bool, float]:
        """Fair Value Gap: imbalância de 3 candles (ICT)."""
        n = len(df)
        if n < 3:
            return False, False, 0.0
        last_close = float(df["close"].iloc[-1])
        bullish_fvg = False
        bearish_fvg = False
        max_size = 0.0
        search = min(n - 2, 12)
        for i in range(n - 3, max(n - search - 2, -1), -1):
            if i < 0 or i + 2 >= n:
                continue
            a_high = float(df["high"].iloc[i])
            a_low = float(df["low"].iloc[i])
            c_high = float(df["high"].iloc[i + 2])
            c_low = float(df["low"].iloc[i + 2])
            # FVG bullish: gap acima do candle A (c.low > a.high)
            if c_low > a_high:
                gap_size = (c_low - a_high) / max(last_close, 1e-9)
                if gap_size >= 0.0001 and last_close >= a_high:
                    bullish_fvg = True
                    max_size = max(max_size, gap_size)
            # FVG bearish: gap abaixo do candle A (c.high < a.low)
            if c_high < a_low:
                gap_size = (a_low - c_high) / max(last_close, 1e-9)
                if gap_size >= 0.0001 and last_close <= a_low:
                    bearish_fvg = True
                    max_size = max(max_size, gap_size)
        return bullish_fvg, bearish_fvg, round(max_size, 6)

    def _order_blocks(
        self, df: pd.DataFrame, atr: pd.Series
    ) -> Tuple[bool, bool, float]:
        """Order Blocks: último candle contra-tendência antes de impulso forte."""
        n = len(df)
        if n < 6:
            return False, False, 0.0
        atr_val = float(atr.iloc[-1]) if not atr.empty and not pd.isna(atr.iloc[-1]) else 0.0
        if atr_val <= 0:
            return False, False, 0.0
        last_close = float(df["close"].iloc[-1])
        bullish_ob = False
        bearish_ob = False
        ob_level = 0.0
        search = min(20, n - 2)
        for i in range(1, search):
            idx = n - 1 - i
            if idx < 1:
                break
            move = float(df["close"].iloc[idx]) - float(df["close"].iloc[idx - 1])
            if abs(move) < atr_val * 1.2:
                continue
            if move > 0:
                # Impulso bullish → OB é o último candle bearish antes dele
                for j in range(idx - 1, max(idx - 5, -1), -1):
                    if j < 0:
                        break
                    if float(df["close"].iloc[j]) < float(df["open"].iloc[j]):
                        ob_h = float(df["high"].iloc[j])
                        ob_l = float(df["low"].iloc[j])
                        if ob_l <= last_close <= ob_h * 1.002:
                            bullish_ob = True
                            ob_level = ob_l
                        break
            else:
                # Impulso bearish → OB é o último candle bullish antes dele
                for j in range(idx - 1, max(idx - 5, -1), -1):
                    if j < 0:
                        break
                    if float(df["close"].iloc[j]) > float(df["open"].iloc[j]):
                        ob_h = float(df["high"].iloc[j])
                        ob_l = float(df["low"].iloc[j])
                        if ob_l * 0.998 <= last_close <= ob_h:
                            bearish_ob = True
                            ob_level = ob_h
                        break
        return bullish_ob, bearish_ob, round(ob_level, 8)

    def _mss(
        self,
        df: pd.DataFrame,
        swing_highs: List[Tuple[int, float]],
        swing_lows: List[Tuple[int, float]],
        trend_m1: str,
    ) -> Tuple[bool, str]:
        """Market Structure Shift: quebra de swing contra a tendência vigente."""
        if not swing_highs and not swing_lows:
            return False, "none"
        last_close = float(df["close"].iloc[-1])
        if trend_m1 == "bear" and swing_highs:
            for _, sh in reversed(swing_highs[-3:]):
                if last_close > sh:
                    return True, "bullish"
        if trend_m1 == "bull" and swing_lows:
            for _, sl in reversed(swing_lows[-3:]):
                if last_close < sl:
                    return True, "bearish"
        return False, "none"

    def _liquidity_grab(
        self,
        df: pd.DataFrame,
        swing_highs: List[Tuple[int, float]],
        swing_lows: List[Tuple[int, float]],
    ) -> Tuple[bool, str]:
        """Liquidity grab: sweep de swing H/L com reversão (stop hunt)."""
        if len(df) < 3:
            return False, "none"
        last = df.iloc[-1]
        prev = df.iloc[-2]
        last_close = float(last["close"])
        last_low = float(last["low"])
        last_high = float(last["high"])
        prev_close = float(prev["close"])
        prev_low = float(prev["low"])
        prev_high = float(prev["high"])
        if swing_lows:
            sl = float(swing_lows[-1][1])
            if last_low < sl and last_close > sl:
                return True, "bullish"
            if prev_low < sl and last_close > sl and last_close > prev_close:
                return True, "bullish"
        if swing_highs:
            sh = float(swing_highs[-1][1])
            if last_high > sh and last_close < sh:
                return True, "bearish"
            if prev_high > sh and last_close < sh and last_close < prev_close:
                return True, "bearish"
        return False, "none"

    def _displacement(
        self, df: pd.DataFrame, atr: pd.Series
    ) -> Tuple[bool, str]:
        """Displacement institucional: candle forte e comprometido relativo ao ATR."""
        if len(df) < 3:
            return False, "none"
        atr_val = float(atr.iloc[-1]) if not atr.empty and not pd.isna(atr.iloc[-1]) else 0.0
        if atr_val <= 0:
            return False, "none"
        for idx in (-3, -2, -1):
            c = df.iloc[idx]
            body = abs(float(c["close"]) - float(c["open"]))
            candle_range = max(float(c["high"]) - float(c["low"]), 1e-9)
            body_ratio = body / candle_range
            if body >= atr_val * 1.5 and body_ratio >= 0.60:
                direction = "bullish" if float(c["close"]) > float(c["open"]) else "bearish"
                return True, direction
        return False, "none"

    def _price_action_patterns(self, df: pd.DataFrame) -> Tuple[str, float]:
        """Detecta padrões de price action: pin bars, engolfantes, marubozu, inside bar, doji."""
        if len(df) < 3:
            return "none", 0.0
        last = df.iloc[-1]
        prev = df.iloc[-2]
        lo = float(last["open"])
        lc = float(last["close"])
        lh = float(last["high"])
        ll = float(last["low"])
        po = float(prev["open"])
        pc = float(prev["close"])
        candle_range = max(lh - ll, 1e-9)
        body = abs(lc - lo)
        body_ratio = body / candle_range
        upper_wick = lh - max(lo, lc)
        lower_wick = min(lo, lc) - ll
        upper_ratio = upper_wick / candle_range
        lower_ratio = lower_wick / candle_range
        close_pos = (lc - ll) / candle_range
        prev_body = abs(pc - po)
        # Pin bar bullish (hammer)
        if lower_ratio >= 0.60 and body_ratio <= 0.30 and close_pos >= 0.55:
            return "bullish_pin_bar", 0.85
        # Pin bar bearish (shooting star)
        if upper_ratio >= 0.60 and body_ratio <= 0.30 and close_pos <= 0.45:
            return "bearish_pin_bar", 0.85
        # Engolfante bullish
        if lc > lo and pc < po and lc > po and lo < pc and body >= prev_body * 0.8:
            return "bullish_engulfing", 0.80
        # Engolfante bearish
        if lc < lo and pc > po and lc < po and lo > pc and body >= prev_body * 0.8:
            return "bearish_engulfing", 0.80
        # Marubozu bullish
        if lc > lo and body_ratio >= 0.78 and lower_ratio <= 0.12 and upper_ratio <= 0.12:
            return "bullish_marubozu", 0.70
        # Marubozu bearish
        if lc < lo and body_ratio >= 0.78 and lower_ratio <= 0.12 and upper_ratio <= 0.12:
            return "bearish_marubozu", 0.70
        # Inside bar (compressão)
        if lh <= float(prev["high"]) * 1.001 and ll >= float(prev["low"]) * 0.999:
            return "inside_bar", 0.40
        # Doji (indecisão)
        if body_ratio <= 0.12:
            return "doji", 0.35
        return "none", 0.0

    def _trend_strength(self, df: pd.DataFrame, period: int = 14) -> float:
        """Price Efficiency Ratio como proxy de ADX (0–1, maior = tendência mais forte)."""
        n = min(period, len(df) - 1)
        if n < 5:
            return 0.5
        close = df["close"]
        directional = abs(float(close.iloc[-1]) - float(close.iloc[-(n + 1)]))
        changes = close.pct_change().abs().tail(n)
        total_path = float(changes.sum()) * float(abs(close.iloc[-1]))
        if total_path <= 0:
            return 0.0
        return round(min(1.0, directional / total_path), 3)

    # ── Cálculo principal ─────────────────────────────────────────────────

    def calculate(self, candles: List[Candle]) -> Dict[str, object]:
        df = pd.DataFrame([c.to_dict() for c in candles])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)

        # ── Indicadores existentes ───────────────────────────────────────
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
        recent_moves = (
            (df["close"].tail(8) - df["open"].tail(8)).abs()
            / df["close"].tail(8).replace(0, 1e-9)
        )
        baseline_move = (
            float(recent_moves.iloc[:-1].mean()) if len(recent_moves) > 1 else candle_move
        )
        expansion_ratio = candle_move / max(baseline_move, 1e-9)
        moved_too_fast = candle_move > 0.0022 or (body_ratio > 0.68 and expansion_ratio > 1.5)
        explosive_expansion = candle_move > 0.0034 or expansion_ratio > 1.9
        late_entry_risk = moved_too_fast and (
            (trend_m1 == "bull" and close_position > 0.78)
            or (trend_m1 == "bear" and close_position < 0.22)
        )
        recent_range = (
            (df["high"].tail(8).max() - df["low"].tail(8).min())
            / max(df["close"].iloc[-1], 1e-9)
        )
        is_sideways = recent_range < 0.0022

        m5 = self._aggregate_to_m5(df)
        trend_m5 = "neutral"
        if m5 is not None:
            m5["ema9"] = m5["close"].ewm(span=9).mean()
            m5["ema21"] = m5["close"].ewm(span=21).mean()
            trend_m5 = "bull" if m5["ema9"].iloc[-1] > m5["ema21"].iloc[-1] else "bear"

        ema_spread = (
            abs(df["ema9"].iloc[-1] - df["ema21"].iloc[-1]) / max(df["close"].iloc[-1], 1e-9)
        )
        if trend_m5 == trend_m1 and ema_spread >= 0.0010:
            trend_quality_signal = "forte"
        elif trend_m5 == trend_m1 and ema_spread >= 0.00045:
            trend_quality_signal = "aceitavel"
        else:
            trend_quality_signal = "fragil"

        # ── ATR ──────────────────────────────────────────────────────────
        atr_series = self._atr(df, period=14)
        atr_val = (
            float(atr_series.iloc[-1])
            if not atr_series.empty and not pd.isna(atr_series.iloc[-1])
            else 0.0
        )
        atr_pct = round(atr_val / max(float(df["close"].iloc[-1]), 1e-9), 6)

        # ── Swing points ──────────────────────────────────────────────────
        swing_bars = 3 if len(df) >= 20 else 2
        swing_highs, swing_lows = self._swing_points(df, bars=swing_bars)
        last_close = float(df["close"].iloc[-1])
        swing_high_recent = float(swing_highs[-1][1]) if swing_highs else 0.0
        swing_low_recent = float(swing_lows[-1][1]) if swing_lows else 0.0

        proximity = atr_val * 0.5 if atr_val > 0 else last_close * 0.0015
        near_swing_high = swing_high_recent > 0 and abs(last_close - swing_high_recent) <= proximity
        near_swing_low = swing_low_recent > 0 and abs(last_close - swing_low_recent) <= proximity

        structure_break = False
        structure_break_direction = "none"
        if swing_highs and last_close > swing_highs[-1][1]:
            structure_break = True
            structure_break_direction = "bullish"
        elif swing_lows and last_close < swing_lows[-1][1]:
            structure_break = True
            structure_break_direction = "bearish"

        # ── SMC / ICT ────────────────────────────────────────────────────
        ob_bullish, ob_bearish, ob_level = self._order_blocks(df, atr_series)
        fvg_bull, fvg_bear, fvg_size = self._fvg(df)
        mss_detected, mss_direction = self._mss(df, swing_highs, swing_lows, trend_m1)
        liq_grab, liq_direction = self._liquidity_grab(df, swing_highs, swing_lows)
        disp, disp_direction = self._displacement(df, atr_series)

        # ── Price action avançado ─────────────────────────────────────────
        pa_pattern, pa_strength = self._price_action_patterns(df)

        # ── Força de tendência ────────────────────────────────────────────
        trend_str = self._trend_strength(df, period=14)

        return {
            # Existentes
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
            # Novos
            "atr": round(atr_val, 8),
            "atr_pct": atr_pct,
            "swing_high_recent": swing_high_recent,
            "swing_low_recent": swing_low_recent,
            "near_swing_high": near_swing_high,
            "near_swing_low": near_swing_low,
            "structure_break": structure_break,
            "structure_break_direction": structure_break_direction,
            "order_block_bullish": ob_bullish,
            "order_block_bearish": ob_bearish,
            "order_block_level": ob_level,
            "fvg_bullish": fvg_bull,
            "fvg_bearish": fvg_bear,
            "fvg_size_pct": fvg_size,
            "mss_detected": mss_detected,
            "mss_direction": mss_direction,
            "liquidity_grab": liq_grab,
            "liquidity_grab_direction": liq_direction,
            "displacement": disp,
            "displacement_direction": disp_direction,
            "price_action_pattern": pa_pattern,
            "pattern_strength": pa_strength,
            "trend_strength": trend_str,
        }
