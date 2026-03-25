from signal_alignment_engine import SignalAlignmentEngine

try:
    from decision_engine import DecisionEngine
except Exception:
    DecisionEngine = None

try:
    from signal_engine_original import SignalEngine as OriginalSignalEngine
except Exception:
    OriginalSignalEngine = None


class SignalEngine:
    """
    Wrapper seguro do SignalEngine original.
    Para usar:
    - renomeie seu signal_engine.py atual para signal_engine_original.py
    - coloque este arquivo como signal_engine.py
    """

    def __init__(self, learning):
        if OriginalSignalEngine is None:
            raise ImportError("signal_engine_original.py não encontrado")
        self._original = OriginalSignalEngine(learning)
        self._alignment = SignalAlignmentEngine()
        self._decision_engine = DecisionEngine(learning) if DecisionEngine else None

    def __getattr__(self, item):
        return getattr(self._original, item)

    def generate_signals(self, market):
        raw = self._original.generate_signals(market)
        if not raw or not self._decision_engine:
            return raw
        try:
            candidates = []
            for item in market:
                indicators = dict(item.get("indicators", {}))
                decision = self._decision_engine.decide(item.get("asset"), indicators)
                candidates.append(decision)
            if not candidates:
                return raw
            candidates.sort(key=lambda x: (x.get("score", 0), x.get("confidence", 0)), reverse=True)
            dominant = candidates[0]
            return self._alignment.apply(raw, dominant)
        except Exception:
            return raw
