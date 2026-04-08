from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot
from alpha_hive.market.indicators import IndicatorEngine

class FeatureEngine:
    def __init__(self):
        self.indicators = IndicatorEngine()

    def extract(self, snapshot: MarketSnapshot) -> MarketFeatures:
        data = self.indicators.calculate(snapshot.candles_m1)
        return MarketFeatures(
            asset=snapshot.asset,
            regime=str(data["regime"]),
            trend_m1=str(data["trend_m1"]),
            trend_m5=str(data["trend_m5"]),
            rsi=float(data["rsi"]),
            pattern=data["pattern"],
            breakout=bool(data["breakout"]),
            breakout_quality=str(data["breakout_quality"]),
            rejection=bool(data["rejection"]),
            rejection_quality=str(data["rejection_quality"]),
            volatility=bool(data["volatility"]),
            moved_too_fast=bool(data["moved_too_fast"]),
            late_entry_risk=bool(data["late_entry_risk"]),
            explosive_expansion=bool(data["explosive_expansion"]),
            is_sideways=bool(data["is_sideways"]),
            trend_quality_signal=str(data["trend_quality_signal"]),
            data_quality_score=float(snapshot.data_quality_score),
            provider=snapshot.provider,
            market_type=snapshot.market_type,
        )
