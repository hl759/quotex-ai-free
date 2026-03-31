class SignalAlignmentEngine:
    """
    Filtra e prioriza sinais com base na decisão dominante.
    Atua no backend sem precisar alterar app.py.
    """

    def _signal_direction(self, signal):
        return str(signal.get("signal", signal.get("direction", ""))).upper()

    def _decision_direction(self, decision):
        return str(decision.get("direction", "")).upper()

    def _decision_strength(self, decision):
        d = str(decision.get("decision", ""))
        if d == "ENTRADA_FORTE":
            return "strong"
        if d == "ENTRADA_CAUTELA":
            return "caution"
        if d == "OBSERVAR":
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
                s = self._append_reason(s, f"Alinhado com decisão dominante {decision_direction}")
                aligned.append(s)
            elif direction in ("CALL", "PUT"):
                s = dict(signal)
                s["score"] = round(max(0.0, float(s.get("score", 0)) - (0.55 if decision_strength == "strong" else 0.25)), 2)
                s["confidence"] = max(50, int(s.get("confidence", 50)) - (10 if decision_strength == "strong" else 4))
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
