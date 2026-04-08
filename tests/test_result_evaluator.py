from alpha_hive.audit.result_evaluator import ResultEvaluator
from alpha_hive.core.contracts import Candle, FinalDecision

def test_result_evaluator_returns_outcome():
    decision = FinalDecision(asset="BTCUSDT", state="OFFENSE", decision="ENTRADA_FORTE", direction="CALL", confidence=80, score=3.4, setup_quality="premium", consensus_quality="prime", execution_permission="LIBERADO", suggested_stake=10.0, risk_pct=0.01, provider="binance", market_type="crypto")
    candles = [Candle(ts="1", open=100, high=101, low=99, close=100, volume=1), Candle(ts="2", open=100, high=102, low=99.5, close=101, volume=1)]
    outcome = ResultEvaluator().evaluate(decision, candles)
    assert outcome is not None
    assert outcome.result == "WIN"
