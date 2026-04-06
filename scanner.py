import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import CRYPTO_ASSETS, FOREX_ASSETS, METALS_ASSETS, TWELVE_BATCH_SIZE, TWELVE_SCAN_INTERVAL_SECONDS, SCANNER_MAX_WORKERS
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


    def _provider_metadata(self, asset, provider):
        provider_text = str(provider or "auto").lower()
        market_type = "crypto" if asset in CRYPTO_ASSETS else ("forex" if asset in FOREX_ASSETS else ("metals" if asset in METALS_ASSETS else "unknown"))
        trust = 1.0
        fallback = False

        if "cache" in provider_text:
            trust -= 0.03
        if provider_text.startswith("binance"):
            trust = min(trust, 1.0)
        elif provider_text.startswith("finnhub"):
            trust = min(trust, 0.97)
        elif provider_text.startswith("twelve"):
            trust = min(trust, 0.95)
        elif provider_text.startswith("alpha"):
            trust = min(trust, 0.92)
        elif provider_text.startswith("yahoo"):
            trust = min(trust, 0.78 if market_type == "crypto" else 0.82)
            fallback = True
        elif provider_text in ("auto", "unknown", ""):
            trust = min(trust, 0.75)
            fallback = True
        else:
            trust = min(trust, 0.84)
            fallback = True

        return {
            "provider": provider or "auto",
            "provider_trust_score": round(max(0.55, min(1.0, trust)), 2),
            "provider_is_fallback": bool(fallback),
            "market_type": market_type,
        }

    def _scan_one(self, asset):
        candles = self.data.get_candles(asset, interval="1min", outputsize=50)
        if not candles:
            return None
        indicators = self.indicators.calculate(candles)
        provider = self.data.last_provider_used.get(asset, "auto")
        provider_meta = self._provider_metadata(asset, provider)
        indicators.update(provider_meta)
        return {
            "asset": asset,
            "candles": candles,
            "indicators": indicators,
            **provider_meta,
        }

    def scan_assets(self):
        results = []
        active_assets = list(CRYPTO_ASSETS)

        if self._should_scan_slow_now():
            active_assets += self._get_slow_batch()

        if not active_assets:
            return results

        max_workers = max(1, min(int(SCANNER_MAX_WORKERS or 3), len(active_assets)))
        ordered = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._scan_one, asset): idx for idx, asset in enumerate(active_assets)}
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
