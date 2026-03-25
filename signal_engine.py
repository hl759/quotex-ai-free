from datetime import datetime, timedelta, timezone

BRAZIL_TZ = timezone(timedelta(hours=-3))


class SignalAlignmentEngine:
    """
    Alinha os sinais com a decisão dominante sem depender de rename
    e sem alterar app.py.
    """

    def _signal_direction(self, signal):
        return str(signal.get("signal", signal.get("direction", ""))).upper()

    def _decision_direction(self, decision):
        return str(decision.get("direction", "")).upper()

    def _decision_strength(self, decision):
        text = str(decision.get("decision", ""))
        if text == "ENTRADA_FORTE":
            return "strong"
        if text == "ENTRADA_CAUTELA":
            return "caution"
        if text == "OBSERVAR":
            return "observe"
        return "none"

    def _append_reason(self, signal, text):
        s = dict(signal)
        reason = s.get("reason", [])
        if isinstance(reason, list):
            reason = list(reason)
            reason.append(text)
        elif reason:
            reason = [str(reason), text]
        else:
            reason = [text]
        s["reason"] = reason
        return s

    def apply(self, signals, dominant_decision):
        if not signals:
            return []

        decision_direction = self._decision_direction(dominant_decision)
        decision_strength = self._decision_strength(dominant_decision)

        if decision_direction not in ("CALL", "PUT"):
            return signals

        aligned, neutral, opposite = [], [], []

        for signal in signals:
            direction = self._signal_direction(signal)

            if direction == decision_direction:
                s = dict(signal)
                s["score"] = round(float(s.get("score", 0)) + (0.18 if decision_strength == "strong" else 0.08), 2)
                s["confidence"] = min(95, int(s.get("confidence", 50)) + (4 if decision_strength == "strong" else 2))
                s["confidence_label"] = "FORTE" if s["confidence"] >= 82 else "MÉDIO" if s["confidence"] >= 70 else "CAUTELOSO"
                s = self._append_reason(s, f"Alinhado com decisão dominante {decision_direction}")
                aligned.append(s)
            elif direction in ("CALL", "PUT"):
                s = dict(signal)
                s["score"] = round(max(0.0, float(s.get("score", 0)) - (0.55 if decision_strength == "strong" else 0.25)), 2)
                s["confidence"] = max(50, int(s.get("confidence", 50)) - (10 if decision_strength == "strong" else 4))
                s["confidence_label"] = "FORTE" if s["confidence"] >= 82 else "MÉDIO" if s["confidence"] >= 70 else "CAUTELOSO"
                s = self._append_reason(s, f"Desalinhado com decisão dominante {decision_direction}")
                opposite.append(s)
            else:
                neutral.append(signal)

        if decision_strength == "strong":
            prioritized = aligned if aligned else neutral
        elif decision_strength == "caution":
            prioritized = aligned + neutral
        elif decision_strength == "observe":
            prioritized = aligned + neutral + opposite[:1]
        else:
            prioritized = aligned + neutral + opposite

        prioritized.sort(key=lambda x: (float(x.get("score", 0)), int(x.get("confidence", 0))), reverse=True)
        return prioritized


class SignalEngine:
    def __init__(self, learning_engine):
        self.learning_engine = learning_engine
        self.alignment_engine = SignalAlignmentEngine()

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

    def _build_dominant_decision_from_signals(self, signals):
        if not signals:
            return {"decision": "NAO_OPERAR", "direction": None}

        top = signals[0]
        score = float(top.get("score", 0))
        confidence = int(top.get("confidence", 50))
        direction = top.get("signal")

        if score >= 4.8 or confidence >= 86:
            decision = "ENTRADA_FORTE"
        elif score >= 3.2 or confidence >= 74:
            decision = "ENTRADA_CAUTELA"
        elif score >= 2.2:
            decision = "OBSERVAR"
        else:
            decision = "NAO_OPERAR"

        return {
            "decision": decision,
            "direction": direction
        }

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

        dominant_decision = self._build_dominant_decision_from_signals(signals)
        aligned = self.alignment_engine.apply(signals, dominant_decision)

        return aligned[:self.learning_engine.dynamic_signal_limit()]
