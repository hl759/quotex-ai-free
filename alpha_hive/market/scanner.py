from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import datetime, timezone
from typing import List, Optional

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import MarketSnapshot
from alpha_hive.market.data_manager import DataManager
from alpha_hive.market.reliability_engine import ReliabilityEngine

log = logging.getLogger(__name__)

# Render Free: 40 velas M1 bastam para RSI/ATR/EMA curta e reduzem payload.
_M1_OUTPUTSIZE = int(__import__("os").getenv("M1_OUTPUTSIZE", "40"))
_M5_OUTPUTSIZE = int(__import__("os").getenv("M5_OUTPUTSIZE", "8"))
_CANDLE_MAX_AGE_SECONDS = int(__import__("os").getenv("CANDLE_MAX_AGE_SECONDS", "180"))


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

    def _scan_timeout_seconds(self, asset_count: int, worker_count: int) -> int:
        waves = max(1, (asset_count + worker_count - 1) // worker_count)
        return max(30, min(75, (waves * 10) + 10))

    def _last_candle_age_seconds(self, candles: list) -> Optional[float]:
        if not candles:
            return None
        try:
            ts_raw = str(getattr(candles[-1], "ts", "") or "").strip()[:19]
            if not ts_raw:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(ts_raw, fmt).replace(tzinfo=timezone.utc)
                    return (datetime.now(timezone.utc) - dt).total_seconds()
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def scan_asset(self, asset: str) -> Optional[MarketSnapshot]:
        candles_m1, chain = self.data.get_candles(asset, interval="1min", outputsize=_M1_OUTPUTSIZE)
        if not candles_m1:
            return None

        age = self._last_candle_age_seconds(candles_m1)
        if age is not None and age > _CANDLE_MAX_AGE_SECONDS:
            log.warning("Scanner: %s descartado — último M1 com %.0fs de atraso", asset, age)
            return None

        candles_m5 = self.data.build_m5_from_m1(candles_m1, outputsize=_M5_OUTPUTSIZE)
        if len(candles_m5) < 5:
            # Fallback controlado: só faz uma segunda chamada quando o M5 derivado
            # é realmente insuficiente.
            direct_m5, _ = self.data.get_candles(asset, interval="5min", outputsize=_M5_OUTPUTSIZE)
            if len(direct_m5) > len(candles_m5):
                candles_m5 = direct_m5

        if not candles_m5:
            candles_m5 = candles_m1[-5:]

        provider = self.data.last_provider_used.get(asset, chain[0] if chain else "unknown")
        provider_root = provider.split("-")[0] if provider else "unknown"
        health_score = self.data.health.get(provider_root).score() if provider else 0.5
        dq_score, dq_state, warnings = self.reliability.evaluate(provider, chain, candles_m1, health_score)

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

    def scan_assets(self, assets: Optional[List[str]] = None) -> List[MarketSnapshot]:
        assets = list(assets or SETTINGS.assets)
        if not assets:
            return []
        max_workers = max(1, min(int(SETTINGS.scanner_max_workers), len(assets)))
        out: List[MarketSnapshot] = []
        timeout = self._scan_timeout_seconds(len(assets), max_workers)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self.scan_asset, asset): asset for asset in assets}
            try:
                for future in as_completed(future_map, timeout=timeout):
                    try:
                        snapshot = future.result()
                        if snapshot:
                            out.append(snapshot)
                    except Exception as exc:
                        log.debug("Scanner: erro em ativo (%s)", exc)
            except FuturesTimeoutError:
                log.warning("Scanner: timeout parcial; usando %d snapshots prontos", len(out))
            finally:
                for future in future_map:
                    if not future.done():
                        future.cancel()

        order = {asset: idx for idx, asset in enumerate(assets)}
        out.sort(key=lambda item: order.get(item.asset, 10**9))
        return out

    def release_memory(self) -> None:
        """Libera cache de candles após o ciclo para manter RAM mínima no Render."""
        try:
            self.data.clear_cache()
        except Exception:
            pass
