from datetime import datetime, timedelta, timezone

# UTC-3 (Brasil no seu caso)
BRAZIL_TZ = timezone(timedelta(hours=-3))

class SignalEngine:

    def score_signal(self, ind):
        score = 0
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

        return score, reasons

    def calculate_confidence(self, score):
        confidence = 50 + (score * 10)
        if confidence > 95:
            confidence = 95
        return confidence

    def get_analysis_time(self):
        now_brazil = datetime.now(BRAZIL_TZ)
        return now_brazil.strftime("%H:%M")

    def get_entry_time(self):
        # entrada 1 minuto depois da análise
        now_brazil = datetime.now(BRAZIL_TZ)
        entry_time = (now_brazil + timedelta(minutes=1)).replace(second=0, microsecond=0)
        return entry_time.strftime("%H:%M")

    def get_expiration_time(self):
        # expiração na vela seguinte à entrada
        now_brazil = datetime.now(BRAZIL_TZ)
        expiration_time = (now_brazil + timedelta(minutes=2)).replace(second=0, microsecond=0)
        return expiration_time.strftime("%H:%M")

    def generate_signals(self, market_data):
        signals = []

        for asset in market_data:
            ind = asset["indicators"]
            score, reasons = self.score_signal(ind)

            if score >= 4:
                trend = ind.get("trend", "bull")
                pattern = ind.get("pattern", "")

                signal = "CALL"
                if trend == "bear" or pattern == "bearish":
                    signal = "PUT"

                signals.append({
                    "asset": asset["asset"],
                    "signal": signal,
                    "score": score,
                    "confidence": self.calculate_confidence(score),
                    "timeframe": "M1",
                    "analysis_time": self.get_analysis_time(),
                    "entry_time": self.get_entry_time(),
                    "expiration": self.get_expiration_time(),
                    "generated_at": self.get_analysis_time(),
                    "provider": asset.get("provider", "auto"),
                    "reason": reasons
                })

        signals.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return signals[:5]
