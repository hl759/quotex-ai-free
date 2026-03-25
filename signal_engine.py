from datetime import datetime, timedelta, timezone

try:
    from decision_engine import DecisionEngine
except Exception:
    DecisionEngine = None

BRAZIL_TZ = timezone(timedelta(hours=-3))


class SignalEngine:
    def __init__(self, learning_engine):
        self.learning_engine = learning_engine
        self._decision_engine = DecisionEngine(learning_engine) if DecisionEngine else None

    def _current_hour(self):
        return datetime.now(BRAZIL_TZ).strftime("%H:%M")

    def _consensus_score(self, asset, indicators):
        score = 0
        reasons = []
        direction = None

        m1 = indicators.get("trend_m1")
        m5 = indicators.get("trend_m5")

        if m1 == "bull":
            score += 2
            direction = "CALL"
            reasons.append("Tendência M1 bullish")
        elif m1 == "bear":
            score += 2
            direction = "PUT"
            reasons.append("Tendência M1 bearish")

        if m1 and m5:
            if m1 == m5:
                score += 2
                reasons.append("M1 alinhado com M5")
            else:
                score -= 1
                reasons.append("Conflito M1 vs M5")

        if indicators.get("pattern") == "bullish" and direction == "CALL":
            score += 1
            reasons.append("Padrão bullish")

        if indicators.get("pattern") == "bearish" and direction == "PUT":
            score += 1
            reasons.append("Padrão bearish")

        if indicators.get("rejection"):
            score += 0.5
            reasons.append("Rejeição relevante")

        if indicators.get("volatility"):
            score += 0.5
            reasons.append("Volatilidade saudável")

        if not reasons or score < 2:
            return None  # 🚫 NÃO GERA SINAL SEM CONFLUÊNCIA

        return score, reasons, direction

    def generate_signals(self, market_data):
        signals = []

        for asset in market_data:
            indicators = asset.get("indicators", {})
            result = self._consensus_score(asset["asset"], indicators)

            if not result:
                continue

            score, reasons, direction = result

            confidence = int(50 + score * 10)
            if confidence > 95:
                confidence = 95

            signals.append({
                "asset": asset["asset"],
                "signal": direction,
                "score": round(score, 2),
                "confidence": confidence,
                "confidence_label": "FORTE" if confidence >= 80 else "MÉDIO",
                "reason": reasons,
                "timeframe": "M1",
                "regime": indicators.get("regime", "unknown")
            })

        if not signals:
            return []

        # pega melhor sinal
        signals.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return [signals[0]]
