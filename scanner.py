import time
from config import CRYPTO_ASSETS, FOREX_ASSETS, METALS_ASSETS, TWELVE_BATCH_SIZE, TWELVE_SCAN_INTERVAL_SECONDS
from indicators import IndicatorEngine

class MarketScanner:
    def __init__(self, data_manager):
        self.data = data_manager
        self.indicators = IndicatorEngine()
        self.forex_cursor = 0
        self.last_slow_scan_ts = 0

    def _get_slow_batch(self):
        pool = FOREX_ASSETS + METALS_ASSETS
        if not pool:
            return []
        start = self.forex_cursor
        end = start + TWELVE_BATCH_SIZE
        batch = pool[start:end]
        if len(batch) < TWELVE_BATCH_SIZE:
            batch += pool[:TWELVE_BATCH_SIZE - len(batch)]
        self.forex_cursor = (self.forex_cursor + TWELVE_BATCH_SIZE) % len(pool)
        return batch

    def _should_scan_slow_now(self):
        now = time.time()
        if now - self.last_slow_scan_ts >= TWELVE_SCAN_INTERVAL_SECONDS:
            self.last_slow_scan_ts = now
            return True
        return False

    def scan_assets(self):
        results = []
        active_assets = list(CRYPTO_ASSETS)
        if self._should_scan_slow_now():
            active_assets += self._get_slow_batch()
        for asset in active_assets:
            candles = self.data.get_candles(asset, interval="1min", outputsize=50)
            if not candles:
                continue
            indicators = self.indicators.calculate(candles)
            results.append({
                "asset": asset,
                "candles": candles,
                "indicators": indicators,
                "provider": self.data.last_provider_used.get(asset, "auto")
            })
        return results
