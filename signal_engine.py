from datetime import datetime, timedelta, timezone
import hashlib
from config import BRAZIL_UTC_OFFSET_HOURS

BRAZIL_TZ = timezone(timedelta(hours=BRAZIL_UTC_OFFSET_HOURS))

class SignalEngine:
    def __init__(self, learning_engine):
        self.learning = learning_engine

    def score_signal(self, ind, asset, provider):
        score = 0.0
        reasons = []
        trend = ind.get("trend")
        rsi = ind.get("rsi", 50)
        pattern = ind.get("pattern")
        volatility = ind.get("volatility", False)
        if trend == "bull":
            score += 2
            reasons.append("Tendência de alta alinhada")
        elif trend == "bear":
            score += 2
            reasons.append("Tendência de baixa alinhada")
        if rsi < 30:
            score += 1
            reasons.append("RSI em sobrevenda")
        elif rsi > 70:
            score += 1
            reasons.append("RSI em sobrecompra")
        if pattern == "bullish":
            score += 1
            reasons.append("Padrão de candle bullish")
        elif pattern == "bearish":
            score += 1
            reasons.append("Padrão de candle bearish")
        if volatility:
            score += 1
            reasons.append("Volatilidade presente")
        adaptive_bonus, bonus_text = self.learning.get_adaptive_bonus(asset, provider)
        score += adaptive_bonus
        if bonus_text:
            reasons.append(bonus_text)
        return score, reasons

    def calculate_confidence(self, score):
        confidence = int(50 + (score * 10))
        return 95 if confidence > 95 else confidence

    def build_times(self):
        now_brazil = datetime.now(BRAZIL_TZ)
        analysis_dt = now_brazil.replace(second=0, microsecond=0)
        entry_dt = analysis_dt + timedelta(minutes=1)
        expiration_dt = analysis_dt + timedelta(minutes=2)
        return {
            "analysis_time": analysis_dt.strftime("%H:%M"),
            "entry_time": entry_dt.strftime("%H:%M"),
            "expiration": expiration_dt.strftime("%H:%M"),
            "entry_ts": int(entry_dt.timestamp()),
            "expiration_ts": int(expiration_dt.timestamp()),
        }

    def generate_signal_id(self, asset, signal, entry_ts):
        return hashlib.md5(f"{asset}-{signal}-{entry_ts}".encode()).hexdigest()[:12]

    def generate_signals(self, market_data):
        signals = []
        for asset in market_data:
            score, reasons = self.score_signal(asset["indicators"], asset["asset"], asset.get("provider", "auto"))
            if score >= 4:
                trend = asset["indicators"].get("trend", "bull")
                pattern = asset["indicators"].get("pattern", "")
                direction = "PUT" if trend == "bear" or pattern == "bearish" else "CALL"
                t = self.build_times()
                signals.append({
                    "signal_id": self.generate_signal_id(asset["asset"], direction, t["entry_ts"]),
                    "asset": asset["asset"],
                    "signal": direction,
                    "score": round(score, 2),
                    "confidence": self.calculate_confidence(score),
                    "timeframe": "M1",
                    "analysis_time": t["analysis_time"],
                    "entry_time": t["entry_time"],
                    "expiration": t["expiration"],
                    "entry_ts": t["entry_ts"],
                    "expiration_ts": t["expiration_ts"],
                    "generated_at": t["analysis_time"],
                    "provider": asset.get("provider", "auto"),
                    "reason": reasons
                })
        signals.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return signals[:5]
