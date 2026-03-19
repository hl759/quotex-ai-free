from datetime import datetime, timedelta, timezone

BRAZIL_TZ = timezone(timedelta(hours=-3))

class SignalEngine:
    def __init__(self, learning_engine):
        self.learning_engine = learning_engine

    def _current_hour_bucket(self):
        return datetime.now(BRAZIL_TZ).strftime("%H:%M")

    def score_signal(self, asset_name, ind):
        score = 0.0
        reasons = []

        trend_m1 = ind.get("trend_m1", ind.get("trend", "neutral"))
        trend_m5 = ind.get("trend_m5", "neutral")
        rsi = ind.get("rsi", 50.0)
        pattern = ind.get("pattern")
        regime = ind.get("regime", "unknown")
        volatility = ind.get("volatility", False)
        breakout = ind.get("breakout", False)
        rejection = ind.get("rejection", False)
        moved_too_fast = ind.get("moved_too_fast", False)
        is_sideways = ind.get("is_sideways", False)

        if trend_m1 == "bull":
            score += 2.0
            reasons.append("Tendência M1 bullish")
        elif trend_m1 == "bear":
            score += 2.0
            reasons.append("Tendência M1 bearish")

        if trend_m5 == trend_m1 and trend_m5 in ("bull", "bear"):
            score += 2.1
            reasons.append("M1 alinhado com M5")
        elif trend_m5 in ("bull", "bear") and trend_m1 != trend_m5:
            score -= 1.0
            reasons.append("Conflito entre M1 e M5")

        if trend_m1 == "bull" and rsi <= 40:
            score += 1.0
            reasons.append("RSI favorece CALL")
        elif trend_m1 == "bear" and rsi >= 60:
            score += 1.0
            reasons.append("RSI favorece PUT")
        elif 46 <= rsi <= 54:
            score -= 0.1
            reasons.append("RSI neutro")

        if pattern == "bullish" and trend_m1 == "bull":
            score += 0.7
            reasons.append("Padrão bullish")
        elif pattern == "bearish" and trend_m1 == "bear":
            score += 0.7
            reasons.append("Padrão bearish")

        if breakout:
            score += 0.8
            reasons.append("Breakout limpo")
        if rejection:
            score += 0.5
            reasons.append("Rejeição válida")

        if volatility:
            score += 0.4
            reasons.append("Volatilidade saudável")

        if regime == "trend":
            score += 1.2
            reasons.append("Regime de tendência")
        elif regime == "sideways":
            score -= 0.8
            reasons.append("Mercado lateral")
        elif regime == "chaotic":
            score -= 1.7
            reasons.append("Mercado caótico")
        elif regime == "mixed":
            score += 0.3
            reasons.append("Mercado misto operável")

        if moved_too_fast:
            score -= 0.5
            reasons.append("Preço já andou um pouco")

        if is_sideways:
            score -= 0.5
            reasons.append("Zona de ruído")

        bonus, bonus_reason = self.learning_engine.get_adaptive_bonus(
            asset_name,
            self._current_hour_bucket()
        )
        score += bonus
        if bonus_reason:
            reasons.append(bonus_reason)

        global_bias, bias_reason = self.learning_engine.get_global_bias()
        score += global_bias
        if bias_reason:
            reasons.append(bias_reason)

        rigor_penalty = self.learning_engine.get_rigor_penalty()
        score -= rigor_penalty
        if rigor_penalty > 0:
            reasons.append("Modo cautela")
        elif rigor_penalty < 0:
            reasons.append("Fase confiante controlada")

        if score < 0:
            score = 0

        return round(score, 2), reasons

    def calculate_confidence(self, score):
        c = 50 + int(score * 7)
        if c > 96:
            c = 96
        if c < 54:
            c = 54
        return c

    def generate_signals(self, market_data):
        signals = []
        profile = self.learning_engine.get_calibration_profile()
        min_score = profile["min_score"]
        max_signals = profile["max_signals"]

        for asset in market_data:
            asset_name = asset["asset"]

            if self.learning_engine.should_pause_asset_temporarily(asset_name):
                continue

            score, reasons = self.score_signal(asset_name, asset["indicators"])
            if score < min_score:
                continue

            trend = asset["indicators"].get("trend_m1", asset["indicators"].get("trend", "bull"))
            signal = "PUT" if trend == "bear" else "CALL"

            confidence = self.calculate_confidence(score)
            label = "FORTE" if confidence >= 82 else "MÉDIO" if confidence >= 70 else "CAUTELOSO"

            signals.append({
                "asset": asset_name,
                "signal": signal,
                "score": score,
                "confidence": confidence,
                "confidence_label": label,
                "provider": asset.get("provider", "auto"),
                "reason": reasons,
                "regime": asset["indicators"].get("regime", "unknown"),
            })

        signals.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return signals[:max_signals]
