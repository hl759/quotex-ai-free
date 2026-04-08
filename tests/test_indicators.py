from alpha_hive.core.contracts import Candle
from alpha_hive.market.indicators import IndicatorEngine

def test_indicators_calculate():
    candles = [Candle(ts=str(i), open=100+i*0.1, high=101+i*0.1, low=99+i*0.1, close=100.2+i*0.1, volume=10) for i in range(60)]
    data = IndicatorEngine().calculate(candles)
    assert data["trend_m1"] in ("bull", "bear")
    assert "regime" in data
