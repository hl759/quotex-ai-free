import time
from config import (
    CRYPTO_ASSETS, FOREX_ASSETS, METALS_ASSETS,
    TWELVE_BATCH_SIZE, TWELVE_SCAN_INTERVAL_SECONDS
)
from indicators import IndicatorEngine


class MarketScanner:
    def __init__(self, data_manager, learning_engine=None):
        self.data        = data_manager
        self.indicators  = IndicatorEngine()
        self.learning    = learning_engine
        self.last_slow_scan_ts = 0

    def _should_scan_slow_now(self):
        now = time.time()
        if now - self.last_slow_scan_ts >= TWELVE_SCAN_INTERVAL_SECONDS:
            self.last_slow_scan_ts = now
            return True
        return False

    def _get_forex_batch(self):
        """
        FIX: antes varria 1 ativo por vez (TWELVE_BATCH_SIZE=1).
        Agora varre TODOS os pares Forex + Metais de uma vez.
        """
        pool = FOREX_ASSETS + METALS_ASSETS
        if self.learning:
            eligible = [a for a in pool if not self.learning.should_filter_asset(a)]
            if not eligible:
                eligible = pool[:]
        else:
            eligible = pool[:]
        return eligible

    def scan_assets(self):
        results      = []
        active_assets = list(CRYPTO_ASSETS)

        # FIX: Forex varre todos os pares a cada TWELVE_SCAN_INTERVAL_SECONDS
        if self._should_scan_slow_now():
            forex_batch = self._get_forex_batch()
            active_assets += forex_batch
            print(f"[Scanner] Varrendo Forex+Metais: {forex_batch}")

        print(f"[Scanner] Total de ativos neste scan: {len(active_assets)}")

        for asset in active_assets:
            # FIX: busca M1 e M5 reais separadamente para análise mais precisa
            candles_m1 = self.data.get_candles(asset, interval="1min", outputsize=60)
            if not candles_m1:
                print(f"[Scanner] Sem dados M1 para {asset}")
                continue

            # M5 real — busca separada para Forex/Metais via Twelve Data
            # Para Crypto (Binance), agrega M1 em M5 como antes
            candles_m5 = None
            is_crypto = asset.endswith(("USDT", "BUSD", "BTC", "ETH", "BNB"))
            if not is_crypto:
                candles_m5 = self.data.get_candles(asset, interval="5min", outputsize=30)

            indicators = self.indicators.calculate(candles_m1, candles_m5=candles_m5)
            results.append({
                "asset":      asset,
                "candles":    candles_m1,
                "indicators": indicators,
                "provider":   self.data.last_provider_used.get(asset, "auto"),
            })

        return results
