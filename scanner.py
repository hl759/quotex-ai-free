import time
from config import CRYPTO_ASSETS, FOREX_ASSETS, METALS_ASSETS, TWELVE_BATCH_SIZE, TWELVE_SCAN_INTERVAL_SECONDS
from indicators import IndicatorEngine
class MarketScanner:
    def __init__(self, data_manager, learning_engine=None):
        self.data=data_manager; self.indicators=IndicatorEngine(); self.learning=learning_engine; self.forex_cursor=0; self.last_slow_scan_ts=0
    def _get_slow_batch(self):
        pool=FOREX_ASSETS+METALS_ASSETS
        eligible=[a for a in pool if not (self.learning and self.learning.should_filter_asset(a))]
        if not eligible: eligible=pool[:]
        start=self.forex_cursor; end=start+TWELVE_BATCH_SIZE
        batch=eligible[start:end]
        if len(batch)<TWELVE_BATCH_SIZE: batch+=eligible[:TWELVE_BATCH_SIZE-len(batch)]
        self.forex_cursor=(self.forex_cursor+TWELVE_BATCH_SIZE)%max(len(eligible),1)
        return batch
    def _should_scan_slow_now(self):
        now=time.time()
        if now-self.last_slow_scan_ts>=TWELVE_SCAN_INTERVAL_SECONDS: self.last_slow_scan_ts=now; return True
        return False
    def scan_assets(self):
        results=[]; active=list(CRYPTO_ASSETS)
        if self._should_scan_slow_now(): active+=self._get_slow_batch()
        for asset in active:
            candles=self.data.get_candles(asset, interval="1min", outputsize=50)
            if not candles: continue
            indicators=self.indicators.calculate(candles)
            results.append({"asset":asset,"candles":candles,"indicators":indicators,"provider":self.data.last_provider_used.get(asset,"auto")})
        return results
