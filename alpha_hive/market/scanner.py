from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import Candle, MarketSnapshot
from alpha_hive.market.data_manager import DataManager
from alpha_hive.market.reliability_engine import ReliabilityEngine

class MarketScanner:
    def __init__(self, data_manager: Optional[DataManager] = None):
        self.data = data_manager or DataManager()
        self.reliability = ReliabilityEngine()

    def _market_type(self, asset: str) -> str:
        if asset in SETTINGS.assets_crypto:
            return "crypto"
        if asset in SETTINGS.assets_forex:
            return "forex"
        return "metals"

    def scan_asset(self, asset: str) -> Optional[MarketSnapshot]:
        candles_m1, chain = self.data.get_candles(asset, interval="1min", outputsize=50)
        if not candles_m1:
            return None
        candles_m5, _ = self.data.get_candles(asset, interval="5min", outputsize=50)
        provider = self.data.last_provider_used.get(asset, chain[0] if chain else "unknown")
        health_score = self.data.health.get(provider.split("-")[0]).score() if provider else 0.5
        dq_score, dq_state, warnings = self.reliability.evaluate(provider, chain, candles_m1, health_score)
        return MarketSnapshot(
            asset=asset,
            market_type=self._market_type(asset),
            provider=provider,
            provider_fallback_chain=chain,
            data_quality_score=dq_score,
            data_quality_state=dq_state,
            candles_m1=candles_m1,
            candles_m5=candles_m5 or candles_m1[-10:],
            warnings=warnings,
        )

    def scan_assets(self) -> List[MarketSnapshot]:
        assets = SETTINGS.assets
        max_workers = max(1, min(SETTINGS.scanner_max_workers, len(assets)))
        out: List[MarketSnapshot] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self.scan_asset, asset): asset for asset in assets}
            for future in as_completed(future_map):
                snapshot = future.result()
                if snapshot:
                    out.append(snapshot)
        out.sort(key=lambda item: item.asset)
        return out
