from datetime import datetime, timedelta

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

    def next_entry_time(self):
        now = datetime.now()
        nxt = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        return nxt.strftime("%H:%M")

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
                    "entry_time": self.next_entry_time(),
                    "expiration": "Próximo candle",
                    "generated_at": datetime.now().strftime("%H:%M:%S"),
                    "reason": reasons
                })

        signals.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return signals[:5]
