from copy import deepcopy


class BinaryOptionsModule:
    """Wrapper conservador sobre a lógica binária já existente."""

    def __init__(self, decision_engine, signal_engine, self_optimizer=None):
        self.decision_engine = decision_engine
        self.signal_engine = signal_engine
        self.self_optimizer = self_optimizer

    def _to_user_signal(self, direction):
        text = str(direction or "").upper()
        if text == "CALL":
            return "BUY"
        if text == "PUT":
            return "SELL"
        return "WAIT"

    def analyze_market(self, market, capital_state=None):
        decision_candidates = []
        capital_state = capital_state or {}
        for item in market or []:
            indicators = dict(item.get("indicators", {}))
            indicators.update(capital_state)
            decision = self.decision_engine.decide(item.get("asset"), indicators)
            decision["provider"] = item.get("provider", "auto")
            decision_candidates.append((decision, item))

        if not decision_candidates:
            return {
                "mode": "BINARY_MODE",
                "status": "NO_TRADE",
                "asset": "MERCADO",
                "signal": "WAIT",
                "expiration": "M1",
                "confidence": 50,
                "reason": ["Sem dados suficientes no momento"],
                "raw_decision": {"decision": "NAO_OPERAR", "direction": None, "score": 0.0},
            }

        decision_candidates.sort(key=lambda x: (x[0].get("score", 0), x[0].get("confidence", 0)), reverse=True)
        best_decision, matched_market = decision_candidates[0]
        decision = deepcopy(best_decision)
        reasons = list(decision.get("reasons", []))

        adjustment = None
        if self.self_optimizer:
            adjustment = self.self_optimizer.get_mode_adjustments(
                mode="BINARY_MODE",
                asset=decision.get("asset"),
                setup_type=decision.get("strategy_name"),
                market_condition=decision.get("environment_type", decision.get("regime", "unknown")),
                analysis_time=decision.get("analysis_session"),
                capital_state=capital_state,
            )
            if not adjustment.get("allow_trade", True) and decision.get("decision") in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
                decision["decision"] = "OBSERVAR"
                decision["direction"] = None
                reasons.append("Self-Optimization: bloqueio temporário por drawdown/frequência")
            elif decision.get("decision") in ("ENTRADA_FORTE", "ENTRADA_CAUTELA") and int(decision.get("confidence", 50) or 50) < adjustment.get("confidence_floor", 64):
                decision["decision"] = "OBSERVAR"
                decision["direction"] = None
                reasons.append("Self-Optimization: confiança abaixo do piso adaptativo")
            reasons.extend(adjustment.get("reasons", []))

        decision["reasons"] = reasons
        signals = self.signal_engine.generate_signals_from_decision(decision)
        primary_signal = signals[0] if signals else {}

        return {
            "mode": "BINARY_MODE",
            "status": "READY" if decision.get("decision") in ("ENTRADA_FORTE", "ENTRADA_CAUTELA") else "NO_TRADE",
            "asset": decision.get("asset", matched_market.get("asset") if matched_market else "MERCADO"),
            "signal": self._to_user_signal(decision.get("direction")),
            "direction": decision.get("direction"),
            "expiration": "M1",
            "confidence": int(primary_signal.get("confidence", decision.get("confidence", 50)) or 50),
            "reason": primary_signal.get("reason", reasons[:4]),
            "raw_decision": decision,
            "provider": matched_market.get("provider", "auto") if matched_market else "auto",
            "adjustment": adjustment or {},
        }
