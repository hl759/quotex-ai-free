from datetime import datetime, timedelta, timezone

from decision_engine import DecisionEngine

BRAZIL_TZ = timezone(timedelta(hours=-3))


class SignalEngine:
    """
    Confluência total entre aba Sinais e aba Decisão.

    Regra:
    - a aba Sinais passa a nascer do mesmo motor da aba Decisão
    - se a Decisão indicar entrada, a aba Sinais mostra esse mesmo trade
    - se a Decisão indicar não operar, a aba Sinais fica vazia

    Resultado:
    - nunca mais a aba Sinais contradiz a aba Decisão
    - nunca mais a aba Sinais fica vazia quando há decisão forte/cautela
    - sem modo base
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
        return str(decision.get("decision", "")).upper() in ("ENTRADA_FORTE", "ENTRADA_CAUTELA", "OBSERVAR") and str(decision.get("direction", "")).upper() in ("CALL", "PUT")

    def _decision_to_signal(self, asset_name, decision):
        reasons = decision.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = [str(reasons)] if reasons else ["Confluência com decisão dominante"]

        return {
            "asset": asset_name,
            "signal": str(decision.get("direction", "CALL")).upper(),
            "score": round(float(decision.get("score", 0.0)), 2),
            "confidence": int(decision.get("confidence", 50)),
            "confidence_label": self._confidence_label(int(decision.get("confidence", 50))),
            "timeframe": "M1",
            "provider": "decision_engine",
            "reason": reasons,
            "regime": decision.get("regime", "unknown"),
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

        # modo sniper: 1 único sinal, sempre igual ao dominante
        return [signal]
