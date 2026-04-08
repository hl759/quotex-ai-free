from __future__ import annotations

from typing import List

from alpha_hive.audit.result_evaluator import ResultEvaluator
from alpha_hive.core.contracts import Candle, FinalDecision, TradeOutcome

class ResultEngine:
    def __init__(self):
        self.evaluator = ResultEvaluator()

    def evaluate_expired_decision(self, decision: FinalDecision, candles: List[Candle]) -> TradeOutcome | None:
        return self.evaluator.evaluate(decision, candles)
