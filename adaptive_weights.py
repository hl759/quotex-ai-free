class AdaptiveWeights:
    def adjust_score(self, signal, stats):
        score = signal.get("score", 0)
        winrate = stats.get("winrate", 50)

        if winrate > 60:
            score += 1
        elif winrate < 45:
            score -= 1

        if score < 0:
            score = 0

        signal["score"] = score
        return signal
