from datetime import datetime, timedelta, timezone

try:
    from decision_engine import DecisionEngine
except Exception:
    DecisionEngine = None

BRAZIL_TZ = timezone(timedelta(hours=-3))


class SignalAlignmentEngine:
    def _signal_direction(self, signal):
        return str(signal.get("signal", signal.get("direction", ""))).upper()

    def apply_strong_confluence(self, signals, dominant_direction):
        if not signals:
            return []
        if dominant_direction not in ("CALL", "PUT"):
            return signals

        aligned = []
        for s in signals:
            if self._signal_direction(s) == dominant_direction:
                s2 = dict(s)
                reason = s2.get("reason", [])
                if isinstance(reason, list):
                    reason = list(reason)
                    reason.append(f"Confluência forte com decisão dominante {dominant_direction}")
                elif reason:
                    reason = [str(reason), f"Confluência forte com decisão dominante {dominant_direction}"]
                else:
                    reason = [f"Confluência forte com decisão dominante {dominant_direction}"]
                s2["reason"] = reason
                aligned.append(s2)

        aligned.sort(key=lambda x: (float(x.get("score", 0)), int(x.get("confidence", 0))), reverse=True)
        return aligned


class HybridDecisionEngine:
    def select_primary_and_backup(self, signals):
        if not signals:
            return None, None
        ordered = sorted(signals, key=lambda x: (float(x.get("score", 0)), int(x.get("confidence", 0))), reverse=True)
        primary = ordered[0]
        backup = ordered[1] if len(ordered) > 1 else None
        return primary, backup


class DynamicDecisionEngine:
    def evaluate(self, current_signal, backup_signal):
        if not current_signal:
            return {"action": "ABORT"}

        score = float(current_signal.get("score", 0))
        confidence = int(current_signal.get("confidence", 0))

        if score < 2.5 or confidence < 65:
            if backup_signal:
                return {"action": "SWITCH_TO_BACKUP", "signal": backup_signal}
            return {"action": "ABORT"}

        if score >= 4.0 and confidence >= 75:
            return {"action": "KEEP"}

        return {"action": "MONITOR"}


class SignalEngine:
    def __init__(self, learning_engine):
        self.learning_engine = learning_engine
        self.alignment_engine = SignalAlignmentEngine()
        self.hybrid_engine = HybridDecisionEngine()
        self.dynamic_engine = DynamicDecisionEngine()
        self.last_backup = None
        self._decision_engine = DecisionEngine(learning_engine) if DecisionEngine else None

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

        try:
            adaptive_bonus, adaptive_reason = self.learning_engine.get_adaptive_bonus(asset_name, self._current_hour_bucket())
            score += adaptive_bonus
            if adaptive_bonus != 0:
                reasons.append(adaptive_reason)
        except Exception:
            pass

        try:
            rigor_penalty = self.learning_engine.get_rigor_penalty()
            if rigor_penalty:
                score -= rigor_penalty
                reasons.append("Modo rigor elevado")
        except Exception:
            pass

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

    def _dominant_decision_from_market(self, market_data):
        if not self._decision_engine:
            return {"decision": "NAO_OPERAR", "direction": None}

        try:
            candidates = []
            analysis_time = datetime.now(BRAZIL_TZ).strftime("%H:%M")
            weekday = datetime.now(BRAZIL_TZ).weekday()

            for asset in market_data:
                indicators = dict(asset.get("indicators", {}))
                indicators.setdefault("analysis_time", analysis_time)
                indicators.setdefault("weekday", weekday)
                decision = self._decision_engine.decide(asset.get("asset"), indicators)
                candidates.append(decision)

            if not candidates:
                return {"decision": "NAO_OPERAR", "direction": None}

            candidates.sort(key=lambda x: (float(x.get("score", 0)), int(x.get("confidence", 0))), reverse=True)
            best = candidates[0]
            return {
                "decision": best.get("decision", "NAO_OPERAR"),
                "direction": best.get("direction")
            }
        except Exception:
            return {"decision": "NAO_OPERAR", "direction": None}

    def generate_signals(self, market_data):
        signals = []

        for asset in market_data:
            indicators = asset["indicators"]
            asset_name = asset["asset"]

            try:
                if self.learning_engine.should_pause_asset_temporarily(asset_name):
                    continue
            except Exception:
                pass

            score, reasons, direction = self._consensus_score(asset_name, indicators)

            try:
                minimum_score = self.learning_engine.dynamic_minimum_score()
            except Exception:
                minimum_score = 2.0

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

        if not signals:
            self.last_backup = None
            return []

        dominant = self._dominant_decision_from_market(market_data)
        dominant_direction = str(dominant.get("direction") or "").upper()

        aligned = self.alignment_engine.apply_strong_confluence(signals, dominant_direction)

        if not aligned:
            self.last_backup = None
            return []

        primary, backup = self.hybrid_engine.select_primary_and_backup(aligned)
        self.last_backup = backup

        decision = self.dynamic_engine.evaluate(primary, backup)

        if decision["action"] == "SWITCH_TO_BACKUP":
            chosen = decision["signal"]
        elif decision["action"] == "ABORT":
            return []
        else:
            chosen = primary

        return [chosen] if chosen else []
