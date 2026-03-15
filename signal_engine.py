
class SignalEngine:

    def score(self, indicators):
        score = 0

        if indicators["trend"] == "bull":
            score += 2
        if indicators["rsi"] < 30:
            score += 1
        if indicators["pattern"]:
            score += 1
        if indicators["volatility"]:
            score += 1

        return score

    def generate_signals(self, market_data):
        signals = []

        for asset in market_data:
            ind = asset["indicators"]
            score = self.score(ind)

            if score >= 4:
                signals.append({
                    "asset": asset["asset"],
                    "signal": "CALL" if ind["trend"] == "bull" else "PUT",
                    "score": score,
                    "reason": ind
                })

        return signals
