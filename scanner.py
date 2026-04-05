import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import CRYPTO_ASSETS, FOREX_ASSETS, METALS_ASSETS, TWELVE_BATCH_SIZE, TWELVE_SCAN_INTERVAL_SECONDS
from indicators import IndicatorEngine


class MarketScanner:
    def __init__(self, data_manager, learning_engine=None):
        self.data = data_manager
        self.indicators = IndicatorEngine()
        self.learning = learning_engine
        self.forex_cursor = 0
        self.last_slow_scan_ts = 0

    def _get_slow_batch(self):
        pool = FOREX_ASSETS + METALS_ASSETS
        eligible = [a for a in pool if not (self.learning and self.learning.should_filter_asset(a))]
        if not eligible:
            eligible = pool[:]

        start = self.forex_cursor
        end = start + TWELVE_BATCH_SIZE
        batch = eligible[start:end]
        if len(batch) < TWELVE_BATCH_SIZE:
            batch += eligible[:TWELVE_BATCH_SIZE - len(batch)]

        self.forex_cursor = (self.forex_cursor + TWELVE_BATCH_SIZE) % max(len(eligible), 1)
        return batch

    def _should_scan_slow_now(self):
        now = time.time()
        if now - self.last_slow_scan_ts >= TWELVE_SCAN_INTERVAL_SECONDS:
            self.last_slow_scan_ts = now
            return True
        return False

    def _normalize_interval(self, timeframe):
        raw = str(timeframe or "1min").strip().lower()
        mapping = {
            "1m": "1min",
            "1min": "1min",
            "m1": "1min",
            "5m": "5min",
            "5min": "5min",
            "m5": "5min",
        }
        return mapping.get(raw, "1min")

    def _scan_one(self, asset, timeframe="1min", outputsize=50):
        interval = self._normalize_interval(timeframe)
        candles = self.data.get_candles(asset, interval=interval, outputsize=max(50, int(outputsize or 50)))
        if not candles:
            return None
        indicators = self.indicators.calculate(candles)
        return {
            "asset": asset,
            "candles": candles,
            "indicators": indicators,
            "provider": self.data.last_provider_used.get(asset, "auto"),
            "timeframe_code": interval,
        }

    def scan_assets(self, timeframe="1min", assets=None, outputsize=50):
        results = []
        if assets:
            active_assets = [str(a).upper().strip() for a in assets if str(a).strip()]
        else:
            active_assets = list(CRYPTO_ASSETS)
            if self._should_scan_slow_now():
                active_assets += self._get_slow_batch()

        if not active_assets:
            return results

        interval = self._normalize_interval(timeframe)
        max_workers = max(1, min(6, len(active_assets)))
        ordered = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._scan_one, asset, interval, outputsize): idx
                for idx, asset in enumerate(active_assets)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    item = future.result()
                except Exception:
                    item = None
                if item:
                    ordered.append((idx, item))

        ordered.sort(key=lambda pair: pair[0])
        for _, item in ordered:
            results.append(item)
        return results
