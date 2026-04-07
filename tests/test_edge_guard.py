from alpha_hive.core.contracts import Candle, CouncilDecision, MarketFeatures, MarketSnapshot
from alpha_hive.risk.edge_guard import EdgeGuard

def test_edge_guard_blocks_weak_data():
    candles = [Candle(ts=str(i), open=1, high=2, low=0.5, close=1.1, volume=10) for i in range(40)]
    snapshot = MarketSnapshot(asset="EURUSD", market_type="forex", provider="yahoo", provider_fallback_chain=["finnhub", "yahoo"], data_quality_score=0.3, data_quality_state="poor", candles_m1=candles, candles_m5=candles[-10:], warnings=["fallback"])
    features = MarketFeatures(asset="EURUSD", regime="mixed", trend_m1="bull", trend_m5="bull", rsi=55.0, pattern=None, breakout=False, breakout_quality="absent", rejection=False, rejection_quality="absent", volatility=True, moved_too_fast=False, late_entry_risk=False, explosive_expansion=False, is_sideways=False, trend_quality_signal="aceitavel", data_quality_score=0.3, provider="yahoo", market_type="forex")
    council = CouncilDecision("CALL", 0.7, "measured", 2.0, 0.8, "low", None, ["trend"], [])
    risk = EdgeGuard().evaluate(snapshot, features, council, {"summary": {}, "recent_20": {}}, "favoravel")
    assert risk.hard_block is True
