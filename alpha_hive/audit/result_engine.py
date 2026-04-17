from __future__ import annotations

from typing import List, Optional

from alpha_hive.audit.result_evaluator import ResultEvaluator
from alpha_hive.core.contracts import Candle, FinalDecision, TradeOutcome


class ResultEngine:
    def __init__(self):
        self.evaluator = ResultEvaluator()

    def evaluate_expired_decision(
        self,
        decision: FinalDecision,
        candles: List[Candle],
        analysis_ts: Optional[float] = None,
        entry_ts: Optional[float] = None,
        expiration_ts: Optional[float] = None,
        delay_seconds: int = 0,
    ) -> TradeOutcome | None:
        return self.evaluator.evaluate(
            decision=decision,
            candles=candles,
            delay_seconds=delay_seconds,
            analysis_ts=analysis_ts,
            entry_ts=entry_ts,
            expiration_ts=expiration_ts,
        )
