class ResultEngine:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def evaluate_expired_signal(self, signal, candles):
        return self.evaluator.evaluate(signal, candles)
