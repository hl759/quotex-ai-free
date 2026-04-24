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

# 60 velas M1 = 60 minutos de histórico.
# Suficiente para ATR(14), RSI(14), swing structure, FVG, Order Blocks e MSS.
_M1_OUTPUTSIZE = 60
_M5_OUTPUTSIZE = 12

# Candle M1 com mais de 120s de idade indica mercado fechado ou API atrasada.
# Nesses casos o snapshot é descartado (requisito: não usar dados atrasados).
_CANDLE_MAX_AGE_SECONDS = 120


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
        """Deadline global do lote. Adaptativo para não derrubar scans parciais."""
        waves = max(1, (asset_count + worker_count - 1) // worker_count)
        return max(45, min(105, (waves * 12) + 10))

    def _last_candle_age_seconds(self, candles: list) -> Optional[float]:
        """Retorna a idade em segundos do último candle (index -1 = mais recente).
        Retorna None se não for possível determinar a idade."""
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
        candles_m1, chain = self.data.get_candles(
            asset, interval="1min", outputsize=_M1_OUTPUTSIZE
        )
        if not candles_m1:
            return None

        # Valida frescor: descarta snapshot se o último candle fechado for muito antigo.
        # Isso impede gerar sinais com dados de mercado fechado ou API com atraso grave.
        age = self._last_candle_age_seconds(candles_m1)
        if age is not None and age > _CANDLE_MAX_AGE_SECONDS:
            log.warning(
                "Scanner: %s descartado — último candle M1 com %.0fs de atraso (max %ds)",
                asset, age, _CANDLE_MAX_AGE_SECONDS,
            )
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

        if age is not None:
            log.debug("Scanner: %s ok — candle_age=%.0fs dq=%.2f provider=%s", asset, age, dq_score, provider)

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
        if assets is None:
            assets = SETTINGS.assets
        max_workers = max(1, min(SETTINGS.scanner_max_workers, len(assets)))
        out: List[MarketSnapshot] = []
        scan_timeout = self._scan_timeout_seconds(len(assets), max_workers)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self.scan_asset, asset): asset
                for asset in assets
            }
            try:
                for future in as_completed(future_map, timeout=scan_timeout):
                    try:
                        snapshot = future.result()
                        if snapshot:
                            out.append(snapshot)
                    except Exception:
                        pass
            except FuturesTimeoutError:
                # Em Render Free alguns ativos podem atrasar o batch.
                # Retorna o que ficou pronto em vez de falhar tudo.
                pass
            finally:
                for future in future_map:
                    if not future.done():
                        future.cancel()

        asset_order = {asset: idx for idx, asset in enumerate(assets)}
        out.sort(key=lambda item: asset_order.get(item.asset, 10**9))
        return out
