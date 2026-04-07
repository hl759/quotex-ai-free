from alpha_hive.core.contracts import Candle, MarketSnapshot
from alpha_hive.intelligence.feature_engine import FeatureEngine
from alpha_hive.specialists.trend_specialist import TrendSpecialist

def test_trend_specialist_returns_vote():
    candles = [Candle(ts=str(i), open=100+i*0.1, high=101+i*0.1, low=99+i*0.1, close=100.3+i*0.1, volume=10) for i in range(60)]
    snapshot = MarketSnapshot(asset="BTCUSDT", market_type="crypto", provider="binance", provider_fallback_chain=["binance"], data_quality_score=0.9, data_quality_state="high", candles_m1=candles, candles_m5=candles[-12:], warnings=[])
    features = FeatureEngine().extract(snapshot)
    vote = TrendSpecialist().evaluate(snapshot, features)
    assert vote.specialist == "trend"
    assert vote.setup_quality in ("fragil", "monitorado", "favoravel", "premium")
