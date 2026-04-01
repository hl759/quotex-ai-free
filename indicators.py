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

    def _breakout(self, df):
        if len(df) < 6:
            return False
        prev_high = df["high"].iloc[-6:-1].max()
        prev_low = df["low"].iloc[-6:-1].min()
        last = df.iloc[-1]
        return bool(last["close"] > prev_high or last["close"] < prev_low)

    def _rejection(self, df):
        if len(df) < 2:
            return False
        last = df.iloc[-1]
        candle_range = max(last["high"] - last["low"], 1e-9)
        upper_wick = last["high"] - max(last["open"], last["close"])
        lower_wick = min(last["open"], last["close"]) - last["low"]
        return bool(upper_wick / candle_range > 0.45 or lower_wick / candle_range > 0.45)

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
        breakout = self._breakout(df)
        rejection = self._rejection(df)

        last = df.iloc[-1]
        candle_move = abs(last["close"] - last["open"]) / max(last["close"], 1e-9)
        moved_too_fast = candle_move > 0.0025

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
            "breakout": breakout,
            "rejection": rejection,
            "moved_too_fast": moved_too_fast,
            "is_sideways": is_sideways
        }
