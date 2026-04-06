import math
import pandas as pd


class IndicatorEngine:
    def _rsi_series(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, 1e-9)
        return 100 - (100 / (1 + rs))

    def _aggregate_to_m5(self, df):
        if len(df) < 5:
            return None
        tmp = df.copy()
        tmp["grp"] = list(range(len(tmp)))[::-1]
        tmp["grp"] = tmp["grp"] // 5
        agg = tmp.groupby("grp", sort=False).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        })
        agg = agg.iloc[::-1].reset_index(drop=True)
        if len(agg) < 3:
            return None
        return agg

    def _detect_pattern(self, df):
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

    def _regime(self, df):
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

    def _last_candle_metrics(self, df):
        last = df.iloc[-1]
        candle_range = max(last["high"] - last["low"], 1e-9)
        body = abs(last["close"] - last["open"])
        body_ratio = body / candle_range
        upper_wick = last["high"] - max(last["open"], last["close"])
        lower_wick = min(last["open"], last["close"]) - last["low"]
        upper_wick_ratio = max(0.0, upper_wick / candle_range)
        lower_wick_ratio = max(0.0, lower_wick / candle_range)
        close_location = (last["close"] - last["low"]) / candle_range
        move_pct = body / max(last["close"], 1e-9)
        direction = "bull" if last["close"] >= last["open"] else "bear"
        return {
            "candle_range": candle_range,
            "body_ratio": round(body_ratio, 4),
            "upper_wick_ratio": round(upper_wick_ratio, 4),
            "lower_wick_ratio": round(lower_wick_ratio, 4),
            "close_location": round(close_location, 4),
            "move_pct": round(move_pct, 5),
            "direction": direction,
        }

    def _breakout_metrics(self, df, last_metrics):
        if len(df) < 6:
            return {
                "breakout": False,
                "breakout_direction": None,
                "breakout_quality": "ausente",
                "breakout_strength": 0.0,
            }
        prev_high = df["high"].iloc[-6:-1].max()
        prev_low = df["low"].iloc[-6:-1].min()
        last = df.iloc[-1]
        direction = None
        distance = 0.0
        if last["close"] > prev_high:
            direction = "bull"
            distance = (last["close"] - prev_high) / max(last["close"], 1e-9)
        elif last["close"] < prev_low:
            direction = "bear"
            distance = (prev_low - last["close"]) / max(last["close"], 1e-9)

        if not direction:
            return {
                "breakout": False,
                "breakout_direction": None,
                "breakout_quality": "ausente",
                "breakout_strength": 0.0,
            }

        body_ratio = last_metrics["body_ratio"]
        close_location = last_metrics["close_location"]
        close_extreme_ok = close_location >= 0.68 if direction == "bull" else close_location <= 0.32
        if body_ratio >= 0.62 and close_extreme_ok and distance >= 0.00018:
            quality = "limpo"
            strength = 1.0
        elif body_ratio >= 0.48 and close_extreme_ok:
            quality = "aceitavel"
            strength = 0.62
        else:
            quality = "fraco"
            strength = 0.28
        return {
            "breakout": True,
            "breakout_direction": direction,
            "breakout_quality": quality,
            "breakout_strength": round(strength, 2),
        }

    def _rejection_metrics(self, df, last_metrics):
        if len(df) < 2:
            return {
                "rejection": False,
                "rejection_direction": None,
                "rejection_quality": "ausente",
            }
        body_ratio = last_metrics["body_ratio"]
        upper = last_metrics["upper_wick_ratio"]
        lower = last_metrics["lower_wick_ratio"]
        close_location = last_metrics["close_location"]

        bullish = lower >= 0.46 and close_location >= 0.58 and body_ratio >= 0.18
        bearish = upper >= 0.46 and close_location <= 0.42 and body_ratio >= 0.18

        if bullish:
            quality = "limpa" if lower >= 0.54 and close_location >= 0.66 else "aceitavel"
            return {"rejection": True, "rejection_direction": "bull", "rejection_quality": quality}
        if bearish:
            quality = "limpa" if upper >= 0.54 and close_location <= 0.34 else "aceitavel"
            return {"rejection": True, "rejection_direction": "bear", "rejection_quality": quality}
        noisy = upper >= 0.45 or lower >= 0.45
        if noisy:
            return {"rejection": False, "rejection_direction": None, "rejection_quality": "ruido"}
        return {"rejection": False, "rejection_direction": None, "rejection_quality": "ausente"}

    def _expansion_metrics(self, df, last_metrics):
        returns = df["close"].pct_change().abs().tail(12)
        baseline = float(returns.median()) if not returns.empty else 0.0
        move_pct = last_metrics["move_pct"]
        explosive = move_pct > max(0.0022, baseline * 2.4 if baseline > 0 else 0.0022)
        extension_pct = abs(df["close"].iloc[-1] - df["ema9"].iloc[-1]) / max(df["close"].iloc[-1], 1e-9)
        late_entry_risk = explosive or (extension_pct > 0.0026 and last_metrics["body_ratio"] >= 0.58)
        return {
            "explosive_expansion": bool(explosive),
            "extension_pct": round(extension_pct, 5),
            "late_entry_risk": bool(late_entry_risk),
        }

    def calculate(self, candles):
        df = pd.DataFrame(candles)
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

        last_metrics = self._last_candle_metrics(df)
        breakout_meta = self._breakout_metrics(df, last_metrics)
        rejection_meta = self._rejection_metrics(df, last_metrics)
        expansion_meta = self._expansion_metrics(df, last_metrics)

        moved_too_fast = last_metrics["move_pct"] > 0.0025
        recent_range = (df["high"].tail(8).max() - df["low"].tail(8).min()) / max(df["close"].iloc[-1], 1e-9)
        is_sideways = recent_range < 0.0022

        m5 = self._aggregate_to_m5(df)
        trend_m5 = "neutral"
        if m5 is not None:
            m5["ema9"] = m5["close"].ewm(span=9).mean()
            m5["ema21"] = m5["close"].ewm(span=21).mean()
            trend_m5 = "bull" if m5["ema9"].iloc[-1] > m5["ema21"].iloc[-1] else "bear"

        return {
            "trend_m1": trend_m1,
            "trend_m5": trend_m5,
            "ema9": float(df["ema9"].iloc[-1]),
            "ema21": float(df["ema21"].iloc[-1]),
            "ema50": float(df["ema50"].iloc[-1]),
            "rsi": float(rsi) if not math.isnan(rsi) else 50.0,
            "pattern": pattern,
            "volatility": volatility,
            "regime": regime,
            "breakout": breakout_meta["breakout"],
            "breakout_direction": breakout_meta["breakout_direction"],
            "breakout_quality": breakout_meta["breakout_quality"],
            "breakout_strength": breakout_meta["breakout_strength"],
            "rejection": rejection_meta["rejection"],
            "rejection_direction": rejection_meta["rejection_direction"],
            "rejection_quality": rejection_meta["rejection_quality"],
            "moved_too_fast": moved_too_fast,
            "explosive_expansion": expansion_meta["explosive_expansion"],
            "late_entry_risk": expansion_meta["late_entry_risk"],
            "extension_pct": expansion_meta["extension_pct"],
            "is_sideways": is_sideways,
            "body_ratio": last_metrics["body_ratio"],
            "close_location": last_metrics["close_location"],
            "upper_wick_ratio": last_metrics["upper_wick_ratio"],
            "lower_wick_ratio": last_metrics["lower_wick_ratio"],
        }
