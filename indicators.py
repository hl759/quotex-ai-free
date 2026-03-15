
import pandas as pd

class IndicatorEngine:

    def calculate(self, candles):

        df = pd.DataFrame(candles)

        df["close"] = df["close"].astype(float)

        df["ema9"] = df["close"].ewm(span=9).mean()
        df["ema21"] = df["close"].ewm(span=21).mean()

        trend = "bull" if df["ema9"].iloc[-1] > df["ema21"].iloc[-1] else "bear"

        rsi = self.rsi(df["close"])

        pattern = self.detect_pattern(df)

        volatility = df["close"].std() > 0

        return {
            "trend": trend,
            "rsi": rsi,
            "pattern": pattern,
            "volatility": volatility
        }

    def rsi(self, series, period=14):

        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

        rs = gain / loss

        return 100 - (100 / (1 + rs)).iloc[-1]

    def detect_pattern(self, df):

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if last["close"] > prev["close"]:
            return "bullish"

        if last["close"] < prev["close"]:
            return "bearish"

        return None
