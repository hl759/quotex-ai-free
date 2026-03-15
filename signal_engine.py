class SignalEngine:
    def score(self, ind):
        score = 0
        if ind["trend"] == "bull":
            score += 2
        if ind["rsi"] < 30:
            score += 1
        if ind["pattern"]:
            score += 1
        if ind["volatility"]:
            score += 1
        return score

    def generate_signals(self, market_data):
        signals = []
        for asset in market_data:
            ind = asset["indicators"]
            score = self.score(ind)
            if score >= 4:
                direction = "CALL" if ind["trend"] == "bull" else "PUT"
                signals.append({
                    "asset": asset["asset"],
                    "signal": direction,
                    "score": score,
                    "reason": ind,
                })
        return signals
        
