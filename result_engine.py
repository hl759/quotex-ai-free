class ResultEngine:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def evaluate_expired_signal(self, signal, candles):
        """
        Avalia um sinal somente depois da expiração.
        Usa o result_evaluator existente, mas só quando já passou do horário.
        """
        return self.evaluator.evaluate(signal, candles)
