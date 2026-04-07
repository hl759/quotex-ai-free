from alpha_hive.core.contracts import Candle, MarketSnapshot, SpecialistVote
from alpha_hive.intelligence.feature_engine import FeatureEngine
from alpha_hive.council.council_engine import CouncilEngine

def test_council_builds_consensus():
    candles = [Candle(ts=str(i), open=100+i*0.1, high=101+i*0.1, low=99+i*0.1, close=100.3+i*0.1, volume=10) for i in range(60)]
    snapshot = MarketSnapshot(asset="BTCUSDT", market_type="crypto", provider="binance", provider_fallback_chain=["binance"], data_quality_score=0.95, data_quality_state="high", candles_m1=candles, candles_m5=candles[-12:], warnings=[])
    features = FeatureEngine().extract(snapshot)
    votes = [
        SpecialistVote("trend", "CALL", 1.2, 80, "favoravel", 0.8, False, []),
        SpecialistVote("breakout", "CALL", 1.0, 76, "favoravel", 0.7, False, []),
        SpecialistVote("reversal", "PUT", 0.2, 55, "fragil", 0.2, False, []),
    ]
    decision = CouncilEngine().evaluate(snapshot, features, votes)
    assert decision.consensus_direction == "CALL"
    assert decision.consensus_strength > 0.5
