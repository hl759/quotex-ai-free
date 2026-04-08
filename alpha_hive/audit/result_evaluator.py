from __future__ import annotations

from typing import List, Optional

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import Candle, FinalDecision, TradeOutcome
from alpha_hive.core.ids import new_uid

class ResultEvaluator:
    def _extract_close(self, candle: Candle) -> float:
        return float(candle.close)

    def evaluate(self, decision: FinalDecision, candles: List[Candle], delay_seconds: int = 0, payout: Optional[float] = None) -> TradeOutcome | None:
        if decision.direction not in ("CALL", "PUT") or len(candles) < 2:
            return None
        payout = float(payout if payout is not None else SETTINGS.default_payout)
        entry = candles[-2]
        exit_ = candles[-1]
        entry_price = self._extract_close(entry)
        exit_price = self._extract_close(exit_)
        if decision.direction == "CALL":
            result = "WIN" if exit_price > entry_price else "LOSS" if exit_price < entry_price else "DRAW"
        else:
            result = "WIN" if exit_price < entry_price else "LOSS" if exit_price > entry_price else "DRAW"
        stake = max(0.0, float(decision.suggested_stake or 0.0))
        if result == "WIN":
            gross_pnl = round(stake * payout, 2)
            gross_r = round(payout, 4)
        elif result == "LOSS":
            gross_pnl = round(-stake, 2)
            gross_r = -1.0
        else:
            gross_pnl = 0.0
            gross_r = 0.0
        timing_quality = "late" if "timing" in " ".join(decision.reasons).lower() else "normal"
        return TradeOutcome(
            uid=new_uid("trade"),
            asset=decision.asset,
            direction=decision.direction,
            result=result,
            entry_price=entry_price,
            exit_price=exit_price,
            payout=payout,
            stake=stake,
            gross_pnl=gross_pnl,
            gross_r=gross_r,
            evaluation_mode="candle_close",
            provider=decision.provider,
            state=decision.state,
            consensus_strength=float(decision.council.get("consensus_strength", 0.0) if decision.council else 0.0),
            timing_quality=timing_quality,
            delay_seconds=delay_seconds,
        )
