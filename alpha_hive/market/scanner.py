from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import MarketSnapshot
from alpha_hive.market.data_manager import DataManager
from alpha_hive.market.reliability_engine import ReliabilityEngine

# RENDER FREE: 80 velas 1min (era 260). 80 é suficiente para RSI/MACD/Bollinger.
_M1_OUTPUTSIZE = 50
_M5_OUTPUTSIZE = 20


class MarketScanner:
    def __init__(self, data_manager: Optional[DataManager] = None):
        self.data = data_manager or DataManager()
        self.reliability = ReliabilityEngine()

    def _market_type(self, asset: str) -> str:
        if asset in SETTINGS.assets_crypto or asset in SETTINGS.assets_pure_crypto:
            return "crypto"
        if asset in SETTINGS.assets_forex:
            return "forex"
        return "metals"

    def scan_asset(self, asset: str) -> Optional[MarketSnapshot]:
        candles_m1, chain = self.data.get_candles(
            asset, interval="1min", outputsize=_M1_OUTPUTSIZE
        )
        if not candles_m1:
            return None

        # Constrói M5 a partir do M1 (evita segunda chamada de API)
        candles_m5 = self.data.build_m5_from_m1(candles_m1, outputsize=_M5_OUTPUTSIZE)

        # Só busca M5 direto se realmente insuficiente (mínimo = 8 velas)
        if len(candles_m5) < 8:
            direct_m5, _ = self.data.get_candles(
                asset, interval="5min", outputsize=_M5_OUTPUTSIZE
            )
            if len(direct_m5) > len(candles_m5):
                candles_m5 = direct_m5

        if not candles_m5:
            candles_m5 = (
                self.data.build_m5_from_m1(candles_m1, outputsize=8)
                or candles_m1[-8:]
            )

        provider = self.data.last_provider_used.get(asset, chain[0] if chain else "unknown")
        provider_root = provider.split("-")[0] if provider else "unknown"
        health_score = self.data.health.get(provider_root).score() if provider else 0.5
        dq_score, dq_state, warnings = self.reliability.evaluate(
            provider, chain, candles_m1, health_score
        )

        return MarketSnapshot(
            asset=asset,
            market_type=self._market_type(asset),
            provider=provider,
            provider_fallback_chain=chain,
            data_quality_score=dq_score,
            data_quality_state=dq_state,
            candles_m1=candles_m1,
            candles_m5=candles_m5,
            warnings=warnings,
            display_asset=asset,
            source_symbol=self.data.resolve_source_symbol(asset, provider),
            source_kind=self.data.source_kind_for(asset),
        )

    def scan_assets(self) -> List[MarketSnapshot]:
        assets = SETTINGS.assets
        max_workers = max(1, min(SETTINGS.scanner_max_workers, len(assets)))
        out: List[MarketSnapshot] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self.scan_asset, asset): asset
                for asset in assets
            }
            for future in as_completed(future_map):
                snapshot = future.result()
                if snapshot:
                    out.append(snapshot)

        asset_order = {asset: idx for idx, asset in enumerate(assets)}
        out.sort(key=lambda item: asset_order.get(item.asset, 10**9))
        return out
