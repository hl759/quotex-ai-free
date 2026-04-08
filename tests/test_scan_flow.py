from alpha_hive.core.contracts import Candle, MarketSnapshot
from alpha_hive.services.scan_service import ScanService

def test_scan_service_with_stubbed_scanner(monkeypatch):
    service = ScanService()
    candles = [Candle(ts=str(i), open=100+i*0.1, high=101+i*0.1, low=99+i*0.1, close=100.3+i*0.1, volume=10) for i in range(60)]
    snapshot = MarketSnapshot(asset="BTCUSDT", market_type="crypto", provider="binance", provider_fallback_chain=["binance"], data_quality_score=0.95, data_quality_state="high", candles_m1=candles, candles_m5=candles[-12:], warnings=[])
    monkeypatch.setattr(service.scanner, "scan_assets", lambda: [snapshot])
    result = service.run_once("test")
    assert result["ok"] is True
