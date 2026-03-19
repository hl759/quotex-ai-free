from datetime import datetime, timedelta, timezone

BRAZIL_TZ = timezone(timedelta(hours=-3))


class SignalEngine:
    def __init__(self, learning_engine):
        self.learning_engine = learning_engine

    def _current_hour_bucket(self):
        return datetime.now(BRAZIL_TZ).strftime("%H:%M")

    def _consensus_score(self, asset_name, indicators):
        score = 0.0
        reasons = []

        trend_m1 = indicators.get("trend_m1", "neutral")
        trend_m5 = indicators.get("trend_m5", "neutral")
        rsi = indicators.get("rsi", 50.0)
        pattern = indicators.get("pattern")
        regime = indicators.get("regime", "unknown")
        volatility = indicators.get("volatility", False)
        breakout = indicators.get("breakout", False)
        rejection = indicators.get("rejection", False)
        moved_too_fast = indicators.get("moved_too_fast", False)
        is_sideways = indicators.get("is_sideways", False)

        direction = None

        if trend_m1 == "bull":
            score += 2.2
            reasons.append("Tendência M1 bullish")
            direction = "CALL"
        elif trend_m1 == "bear":
            score += 2.2
            reasons.append("Tendência M1 bearish")
            direction = "PUT"

        if trend_m5 == trend_m1 and trend_m5 in ("bull", "bear"):
            score += 2.0
            reasons.append("M1 alinhado com M5")
        elif trend_m5 in ("bull", "bear") and trend_m1 != trend_m5:
            score -= 1.0
            reasons.append("Conflito entre M1 e M5")

        if rsi <= 32 and direction == "CALL":
            score += 1.2
            reasons.append("RSI favorece CALL")
        elif rsi >= 68 and direction == "PUT":
            score += 1.2
            reasons.append("RSI favorece PUT")
        elif 45 <= rsi <= 55:
            score -= 0.6
            reasons.append("RSI neutro")

        if pattern == "bullish" and direction == "CALL":
            score += 1.0
            reasons.append("Padrão bullish")
        elif pattern == "bearish" and direction == "PUT":
            score += 1.0
            reasons.append("Padrão bearish")

        if breakout:
            score += 0.8
            reasons.append("Breakout limpo")
        if rejection:
            score += 0.7
            reasons.append("Rejeição válida")

        if volatility:
            score += 0.5
            reasons.append("Volatilidade saudável")

        if regime == "trend":
            score += 0.8
            reasons.append("Regime de tendência")
        elif regime == "sideways":
            score -= 1.3
            reasons.append("Mercado lateral")
        elif regime == "chaotic":
            score -= 1.0
            reasons.append("Mercado caótico")

        if is_sideways:
            score -= 1.0
            reasons.append("Filtro anti-lateral ativo")

        if moved_too_fast:
            score -= 1.1
            reasons.append("Preço já andou demais")

        adaptive_bonus, adaptive_reason = self.learning_engine.get_adaptive_bonus(asset_name, self._current_hour_bucket())
        score += adaptive_bonus
        if adaptive_bonus != 0:
            reasons.append(adaptive_reason)

        rigor_penalty = self.learning_engine.get_rigor_penalty()
        if rigor_penalty:
            score -= rigor_penalty
            reasons.append("Modo rigor elevado")

        if score < 0:
            score = 0

        return score, reasons, direction or "CALL"

    def calculate_confidence(self, score, indicators):
        base = 42 + (score * 9)
        if indicators.get("trend_m1") == indicators.get("trend_m5"):
            base += 6
        if indicators.get("regime") == "trend":
            base += 4
        if indicators.get("moved_too_fast"):
            base -= 6
        if indicators.get("is_sideways"):
            base -= 8
        if base > 96:
            base = 96
        if base < 51:
            base = 51
        return int(base)

    def generate_signals(self, market_data):
        signals = []

        for asset in market_data:
            indicators = asset["indicators"]
            asset_name = asset["asset"]

            if self.learning_engine.should_pause_asset_temporarily(asset_name):
                continue

            score, reasons, direction = self._consensus_score(asset_name, indicators)
            minimum_score = self.learning_engine.dynamic_minimum_score()
            if score < minimum_score:
                continue

            confidence = self.calculate_confidence(score, indicators)
            confidence_label = "FORTE" if confidence >= 82 else "MÉDIO" if confidence >= 70 else "CAUTELOSO"

            signals.append({
                "asset": asset_name,
                "signal": direction,
                "score": round(score, 2),
                "confidence": confidence,
                "confidence_label": confidence_label,
                "timeframe": "M1",
                "provider": asset.get("provider", "auto"),
                "reason": reasons,
                "regime": indicators.get("regime", "unknown")
            })

        signals.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return signals[:self.learning_engine.dynamic_signal_limit()]
