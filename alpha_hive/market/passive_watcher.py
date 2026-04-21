from __future__ import annotations
import os, threading, time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple
from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import Candle
from alpha_hive.market.data_manager import DataManager
from alpha_hive.market.reliability_engine import ReliabilityEngine

_PASSIVE_INTERVAL_SECONDS: int = int(os.getenv("PASSIVE_INTERVAL_SECONDS", "120"))
_CANDLE_BUFFER_M1: int = 50
_CANDLE_BUFFER_M5: int = 20
_INTER_ASSET_SLEEP: float = 1.0
_CONTEXT_STALE_SECONDS: float = 480.0

@dataclass
class AssetContext:
    asset: str
    candles_m1: Deque[Candle] = field(default_factory=lambda: deque(maxlen=_CANDLE_BUFFER_M1))
    candles_m5: List[Candle] = field(default_factory=list)
    provider: str = "unknown"
    provider_chain: List[str] = field(default_factory=list)
    data_quality_score: float = 0.5
    data_quality_state: str = "unknown"
    warnings: List[str] = field(default_factory=list)
    source_symbol: str = ""
    source_kind: str = "standard"
    ema9_m1: float = 0.0
    ema21_m1: float = 0.0
    ema50_m1: float = 0.0
    ema9_m5: float = 0.0
    ema21_m5: float = 0.0
    trend_m1: str = "unknown"
    trend_m5: str = "neutral"
    rsi: float = 50.0
    regime: str = "unknown"
    is_sideways: bool = False
    volatility: bool = False
    _rsi_avg_gain: float = 0.0
    _rsi_avg_loss: float = 0.0
    _rsi_initialized: bool = False
    last_updated_ts: float = 0.0
    update_count: int = 0
    is_initialized: bool = False
    last_error: str = ""

    @property
    def age_seconds(self) -> float:
        if self.last_updated_ts <= 0:
            return float("inf")
        return time.time() - self.last_updated_ts

    @property
    def is_fresh(self) -> bool:
        return self.age_seconds < _CONTEXT_STALE_SECONDS

    def to_candle_lists(self) -> Tuple[List[Candle], List[Candle]]:
        return list(self.candles_m1), list(self.candles_m5)


class PassiveWatcher:
    def __init__(self, data_manager: Optional[DataManager] = None):
        self._data = data_manager or DataManager()
        self._reliability = ReliabilityEngine()
        self._contexts: Dict[str, AssetContext] = {
            asset: AssetContext(asset=asset) for asset in SETTINGS.assets
        }
        self._lock = threading.RLock()
        self._started = False
        self._stop_event = threading.Event()
        self._cycle_count: int = 0
        self._last_cycle_ts: float = 0.0
        self._last_cycle_duration_ms: int = 0

    def get_context(self, asset: str) -> Optional[AssetContext]:
        with self._lock:
            return self._contexts.get(asset)

    def get_all_contexts(self) -> Dict[str, AssetContext]:
        with self._lock:
            return dict(self._contexts)

    def ensure_started(self) -> None:
        if self._started:
            return
        t = threading.Thread(target=self._loop, daemon=True, name="passive-watcher")
        t.start()
        self._started = True

    def stop(self) -> None:
        self._stop_event.set()

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            ctxs = dict(self._contexts)
        return {
            "passive_interval_seconds": _PASSIVE_INTERVAL_SECONDS,
            "total_assets": len(ctxs),
            "initialized": sum(1 for c in ctxs.values() if c.is_initialized),
            "fresh": sum(1 for c in ctxs.values() if c.is_fresh),
            "cycle_count": self._cycle_count,
            "last_cycle_ts": self._last_cycle_ts,
            "last_cycle_duration_ms": self._last_cycle_duration_ms,
            "assets": {
                a: {
                    "initialized": c.is_initialized,
                    "age_seconds": round(c.age_seconds, 1),
                    "candles_m1": len(c.candles_m1),
                    "regime": c.regime,
                    "trend_m1": c.trend_m1,
                    "trend_m5": c.trend_m5,
                    "rsi": round(c.rsi, 1),
                    "provider": c.provider,
                    "dq": round(c.data_quality_score, 2),
                    "last_error": c.last_error[:120] if c.last_error else "",
                }
                for a, c in ctxs.items()
            },
        }

    @staticmethod
    def _ema_update(prev: float, price: float, span: int) -> float:
        if prev <= 0.0:
            return price
        alpha = 2.0 / (span + 1)
        return alpha * price + (1.0 - alpha) * prev

    @staticmethod
    def _wilder_rsi_init(closes: List[float], period: int = 14) -> Tuple[float, float, float]:
        if len(closes) < period + 1:
            return 50.0, 0.0, 0.0
        diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0.0) for d in diffs[-period:]]
        losses = [abs(min(d, 0.0)) for d in diffs[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        rs = avg_gain / max(avg_loss, 1e-9)
        return 100.0 - (100.0 / (1.0 + rs)), avg_gain, avg_loss

    @staticmethod
    def _wilder_rsi_update(prev_avg_gain: float, prev_avg_loss: float, new_close: float, prev_close: float, period: int = 14) -> Tuple[float, float, float]:
        diff = new_close - prev_close
        gain = max(diff, 0.0)
        loss = abs(min(diff, 0.0))
        avg_gain = (prev_avg_gain * (period - 1) + gain) / period
        avg_loss = (prev_avg_loss * (period - 1) + loss) / period
        rs = avg_gain / max(avg_loss, 1e-9)
        return 100.0 - (100.0 / (1.0 + rs)), avg_gain, avg_loss

    @staticmethod
    def _regime_fast(candles: Deque[Candle]) -> Tuple[str, bool, bool]:
        if len(candles) < 20:
            return "unknown", False, False
        tail = list(candles)[-20:]
        closes = [float(c.close) for c in tail]
        highs = [float(c.high) for c in tail[-10:]]
        lows = [float(c.low) for c in tail[-10:]]
        last_close = closes[-1]
        if last_close <= 0:
            return "unknown", False, False
        mean = sum(closes[-10:]) / 10
        variance = sum((x - mean) ** 2 for x in closes[-10:]) / 10
        std = variance ** 0.5
        std_pct = std / max(last_close, 1e-9)
        range_pct = (max(highs) - min(lows)) / max(last_close, 1e-9)
        slope = (closes[-1] - closes[-10]) / max(abs(closes[-10]), 1e-9)
        is_sideways = range_pct < 0.0022
        volatility = std_pct > 0.0012
        if std_pct > 0.006:
            regime = "chaotic"
        elif abs(slope) > 0.004 and range_pct > 0.003:
            regime = "trend"
        elif range_pct < 0.0025:
            regime = "sideways"
        else:
            regime = "mixed"
        return regime, is_sideways, volatility

    def _refresh_asset(self, asset: str) -> bool:
        try:
            candles_m1, chain = self._data.get_candles(asset, interval="1min", outputsize=50)
            if not candles_m1:
                return False
            if hasattr(self._data, 'build_m5_from_m1'):
                candles_m5 = self._data.build_m5_from_m1(candles_m1, outputsize=20)
            else:
                candles_m5 = candles_m1[-20:]
            if len(candles_m5) < 8:
                candles_m5 = candles_m1[-8:]
            provider = self._data.last_provider_used.get(asset, chain[0] if chain else "unknown")
            provider_root = provider.split("-")[0] if provider else "unknown"
            health_score = self._data.health.get(provider_root).score()
            dq_score, dq_state, warnings = self._reliability.evaluate(provider, chain, candles_m1, health_score)
            with self._lock:
                ctx = self._contexts[asset]
                current_last_ts = float(ctx.candles_m1[-1].time) if ctx.candles_m1 else 0.0
                new_last_ts = float(candles_m1[-1].time) if candles_m1 else 0.0
                candles_changed = (new_last_ts > current_last_ts) or (not ctx.is_initialized)
                ctx.candles_m1.clear()
                for c in candles_m1:
                    ctx.candles_m1.append(c)
                ctx.candles_m5 = candles_m5
                if candles_changed:
                    closes_m1 = [float(c.close) for c in ctx.candles_m1]
                    if not ctx.is_initialized:
                        if len(closes_m1) >= 50:
                            ema9 = closes_m1[0]; ema21 = closes_m1[0]; ema50 = closes_m1[0]
                            for p in closes_m1[1:]:
                                ema9 = self._ema_update(ema9, p, 9)
                                ema21 = self._ema_update(ema21, p, 21)
                                ema50 = self._ema_update(ema50, p, 50)
                            ctx.ema9_m1 = ema9; ctx.ema21_m1 = ema21; ctx.ema50_m1 = ema50
                        rsi, avg_gain, avg_loss = self._wilder_rsi_init(closes_m1)
                        ctx.rsi = rsi; ctx._rsi_avg_gain = avg_gain; ctx._rsi_avg_loss = avg_loss
                        ctx._rsi_initialized = True
                    else:
                        last_price = closes_m1[-1]
                        prev_price = closes_m1[-2] if len(closes_m1) >= 2 else last_price
                        ctx.ema9_m1 = self._ema_update(ctx.ema9_m1, last_price, 9)
                        ctx.ema21_m1 = self._ema_update(ctx.ema21_m1, last_price, 21)
                        ctx.ema50_m1 = self._ema_update(ctx.ema50_m1, last_price, 50)
                        if ctx._rsi_initialized and prev_price > 0:
                            rsi, avg_gain, avg_loss = self._wilder_rsi_update(ctx._rsi_avg_gain, ctx._rsi_avg_loss, last_price, prev_price)
                            ctx.rsi = rsi; ctx._rsi_avg_gain = avg_gain; ctx._rsi_avg_loss = avg_loss
                    closes_m5 = [float(c.close) for c in ctx.candles_m5]
                    if closes_m5:
                        ema9_m5 = closes_m5[0]; ema21_m5 = closes_m5[0]
                        for p in closes_m5[1:]:
                            ema9_m5 = self._ema_update(ema9_m5, p, 9)
                            ema21_m5 = self._ema_update(ema21_m5, p, 21)
                        ctx.ema9_m5 = ema9_m5; ctx.ema21_m5 = ema21_m5
                    ctx.trend_m1 = "bull" if ctx.ema9_m1 > ctx.ema21_m1 else "bear"
                    ctx.trend_m5 = "bull" if ctx.ema9_m5 > ctx.ema21_m5 else "bear"
                    ctx.regime, ctx.is_sideways, ctx.volatility = self._regime_fast(ctx.candles_m1)
                ctx.provider = provider; ctx.provider_chain = chain
                ctx.data_quality_score = dq_score; ctx.data_quality_state = dq_state
                ctx.warnings = warnings
                ctx.source_symbol = getattr(self._data, 'resolve_source_symbol', lambda a,p: a)(asset, provider)
                ctx.source_kind = getattr(self._data, 'source_kind_for', lambda a: 'standard')(asset)
                ctx.last_updated_ts = time.time(); ctx.update_count += 1
                ctx.is_initialized = True; ctx.last_error = ""
            return True
        except Exception as exc:
            with self._lock:
                if asset in self._contexts:
                    self._contexts[asset].last_error = repr(exc)[:200]
            return False

    def _passive_cycle(self) -> int:
        assets = list(SETTINGS.assets)
        updated = 0
        for asset in assets:
            if self._stop_event.is_set():
                break
            if self._refresh_asset(asset):
                updated += 1
            if not self._stop_event.is_set():
                time.sleep(_INTER_ASSET_SLEEP)
        return updated

    def _loop(self) -> None:
        t0 = time.time()
        self._passive_cycle()
        self._cycle_count += 1
        self._last_cycle_ts = time.time()
        self._last_cycle_duration_ms = int((time.time() - t0) * 1000)
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_PASSIVE_INTERVAL_SECONDS)
            if self._stop_event.is_set():
                break
            t0 = time.time()
            self._passive_cycle()
            self._cycle_count += 1
            self._last_cycle_ts = time.time()
            self._last_cycle_duration_ms = int((time.time() - t0) * 1000)
