# HYBRID SIGNAL ENGINE - v13 etapa híbrida

from datetime import datetime, timedelta, timezone

BRAZIL_TZ = timezone(timedelta(hours=-3))


class HybridDecisionEngine:
    def select_primary_and_backup(self, signals):
        if not signals:
            return None, None

        sorted_signals = sorted(signals, key=lambda x: (x["score"], x["confidence"]), reverse=True)

        primary = sorted_signals[0]
        backup = sorted_signals[1] if len(sorted_signals) > 1 else None

        return primary, backup


class SignalEngine:
    def __init__(self, learning_engine):
        self.learning_engine = learning_engine
        self.hybrid_engine = HybridDecisionEngine()

    def generate_signals(self, market_data):
        signals = []

        for asset in market_data:
            indicators = asset["indicators"]
            asset_name = asset["asset"]

            score = indicators.get("score", 0)
            direction = indicators.get("direction", "CALL")

            signals.append({
                "asset": asset_name,
                "signal": direction,
                "score": score,
                "confidence": 70,
                "confidence_label": "MÉDIO",
                "reason": ["Base signal"],
                "regime": indicators.get("regime", "unknown")
            })

        if not signals:
            return []

        primary, backup = self.hybrid_engine.select_primary_and_backup(signals)

        # Salva backup internamente (pode usar depois)
        self.last_backup = backup

        return [primary] if primary else []
