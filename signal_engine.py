from datetime import datetime, timedelta, timezone

from decision_engine import DecisionEngine

BRAZIL_TZ = timezone(timedelta(hours=-3))


class SignalEngine:
    """
    Confluência total entre aba Sinais e aba Decisão.

    Ajuste desta versão:
    - aba Sinais mostra resumo curto dos motivos
    - aba Decisão continua mostrando todos os motivos completos
    - sem alterar app.py
    """

    def __init__(self, learning_engine):
        self.learning_engine = learning_engine
        self.decision_engine = DecisionEngine(learning_engine)

    def _now_brazil(self):
        return datetime.now(BRAZIL_TZ)

    def _confidence_label(self, confidence):
        if confidence >= 82:
            return "FORTE"
        if confidence >= 70:
            return "MÉDIO"
        return "CAUTELOSO"

    def _is_operable(self, decision):
        return (
            str(decision.get("decision", "")).upper() in ("ENTRADA_FORTE", "ENTRADA_CAUTELA", "OBSERVAR")
            and str(decision.get("direction", "")).upper() in ("CALL", "PUT")
        )

    def _summarize_reasons(self, reasons, direction, regime):
        if not isinstance(reasons, list):
            reasons = [str(reasons)] if reasons else []

        picked = []

        priority_keywords = [
            "Tendência M1 definida",
            "M1 e M5 alinhados",
            "Breakout limpo",
            "Rejeição relevante",
            "Padrão bullish",
            "Padrão bearish",
            "RSI em zona útil",
            "Regime trend favorável",
            "Regime mixed operável",
            "Regime sideways tratável",
            "Consenso forte entre contextos",
            "Consenso leve entre contextos",
            "Context Pattern muito favorável",
            "Context Pattern favorável",
            "Context Intelligence:",
            "Capital Mind:",
            "Estratégia líder:",
        ]

        for keyword in priority_keywords:
            for reason in reasons:
                if keyword in str(reason) and reason not in picked:
                    picked.append(str(reason))
                    break

        if not picked:
            for reason in reasons:
                text = str(reason)
                if text not in picked:
                    picked.append(text)
                if len(picked) >= 4:
                    break

        summary = picked[:4]

        if not summary:
            direction_txt = "CALL" if str(direction).upper() == "CALL" else "PUT"
            summary = [
                f"Direção dominante {direction_txt}",
                f"Regime {regime}",
            ]

        return summary

    def _decision_to_signal(self, asset_name, decision):
        full_reasons = decision.get("reasons", [])
        if not isinstance(full_reasons, list):
            full_reasons = [str(full_reasons)] if full_reasons else []

        direction = str(decision.get("direction", "CALL")).upper()
        regime = decision.get("regime", "unknown")

        summary_reasons = self._summarize_reasons(
            full_reasons,
            direction=direction,
            regime=regime,
        )

        return {
            "asset": asset_name,
            "signal": direction,
            "score": round(float(decision.get("score", 0.0)), 2),
            "confidence": int(decision.get("confidence", 50)),
            "confidence_label": self._confidence_label(int(decision.get("confidence", 50))),
            "timeframe": "M1",
            "provider": "decision_engine",
            "reason": summary_reasons,
            "regime": regime,
        }

    def generate_signals(self, market_data):
        if not market_data:
            return []

        analysis_time = self._now_brazil().strftime("%H:%M")
        weekday = self._now_brazil().weekday()

        candidates = []

        for asset in market_data:
            asset_name = asset.get("asset", "N/A")
            indicators = dict(asset.get("indicators", {}))
            indicators.setdefault("analysis_time", analysis_time)
            indicators.setdefault("weekday", weekday)

            try:
                decision = self.decision_engine.decide(asset_name, indicators)
            except Exception:
                continue

            if self._is_operable(decision):
                candidates.append((asset_name, decision))

        if not candidates:
            return []

        candidates.sort(
            key=lambda x: (
                float(x[1].get("score", 0.0)),
                int(x[1].get("confidence", 0))
            ),
            reverse=True
        )

        best_asset, best_decision = candidates[0]
        signal = self._decision_to_signal(best_asset, best_decision)

        return [signal]
