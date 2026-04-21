from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import Candle
from alpha_hive.market.normalizers import alpha_vantage, binance, finnhub, twelve, yahoo
from alpha_hive.market.provider_health import ProviderHealthRegistry
from alpha_hive.market.provider_router import ProviderRouter


class DataManager:
    def __init__(self) -> None:
        self.cache: Dict[str, Dict[str, object]] = {}
        self.cache_lock = threading.Lock()
        self.last_provider_used: Dict[str, str] = {}
        self.router = ProviderRouter()
        self.health = ProviderHealthRegistry()
        self.request_headers = {
            "User-Agent": "AlphaHiveAI/2.0",
            "Accept": "application/json,text/plain,*/*",
        }
        self.key_usage = [
            {"key": key, "daily": 0, "minute": 0, "minute_window_start": time.time()}
            for key in SETTINGS.twelvedata_keys
        ]
        self.day_marker = datetime.now().astimezone().strftime("%Y-%m-%d")

    def _cache_key(self, provider: str, symbol: str, interval: str) -> str:
        return f"{provider}:{symbol}:{interval}"

    def _get_cache(self, provider: str, symbol: str, interval: str) -> Optional[List[Candle]]:
        with self.cache_lock:
            item = self.cache.get(self._cache_key(provider, symbol, interval))
        if not item or time.time() > float(item["expires_at"]):
            return None
        return item["data"]  # type: ignore[return-value]

    def _set_cache(self, provider: str, symbol: str, interval: str, data: List[Candle]) -> None:
        ttl = 400 if interval == "5min" else 260
        with self.cache_lock:
            self.cache[self._cache_key(provider, symbol, interval)] = {
                "data": data,
                "expires_at": time.time() + ttl,
            }

    def _http_get_json(self, url: str, params: Optional[Dict[str, object]] = None, timeout: int = 4) -> Any:
        try:
            response = requests.get(url, params=params, headers=self.request_headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _remember(self, symbol: str, provider: str) -> None:
        self.last_provider_used[symbol] = provider

    def _trim(self, candles: List[Candle], outputsize: int) -> List[Candle]:
        if outputsize <= 0:
            return candles
        return candles[-outputsize:]

    def _to_twelve_symbol(self, symbol: str) -> str:
        return {
            "EURUSD": "EUR/USD",
            "GBPUSD": "GBP/USD",
            "USDJPY": "USD/JPY",
            "AUDUSD": "AUD/USD",
            "USDCAD": "USD/CAD",
            "USDCHF": "USD/CHF",
            "NZDUSD": "NZD/USD",
            "EURJPY": "EUR/JPY",
            "GBPJPY": "GBP/JPY",
            "EURGBP": "EUR/GBP",
            "GOLD": "XAU/USD",
            "SILVER": "XAG/USD",
        }.get(symbol, symbol)

    def _to_finnhub_symbol(self, symbol: str) -> Optional[str]:
        return {
            "EURUSD": "OANDA:EUR_USD",
            "GBPUSD": "OANDA:GBP_USD",
            "USDJPY": "OANDA:USD_JPY",
            "AUDUSD": "OANDA:AUD_USD",
            "USDCAD": "OANDA:USD_CAD",
            "USDCHF": "OANDA:USD_CHF",
            "NZDUSD": "OANDA:NZD_USD",
            "EURJPY": "OANDA:EUR_JPY",
            "GBPJPY": "OANDA:GBP_JPY",
            "EURGBP": "OANDA:EUR_GBP",
        }.get(symbol)

    def _to_yahoo_symbol(self, symbol: str) -> Optional[str]:
        return {
            "BTCUSDT": "BTC-USD",
            "ETHUSDT": "ETH-USD",
            "BNBUSDT": "BNB-USD",
            "SOLUSDT": "SOL-USD",
            "XRPUSDT": "XRP-USD",
            "ADAUSDT": "ADA-USD",
            "DOGEUSDT": "DOGE-USD",

            "BITCOIN": "BTC-USD",
            "ETHEREUM": "ETH-USD",
            "SOLANA": "SOL-USD",
            "RIPPLE": "XRP-USD",
            "CARDANO": "ADA-USD",
            "DOGECOIN": "DOGE-USD",

            "EURUSD": "EURUSD=X",
            "GBPUSD": "GBPUSD=X",
            "USDJPY": "USDJPY=X",
            "AUDUSD": "AUDUSD=X",
            "USDCAD": "USDCAD=X",
            "USDCHF": "USDCHF=X",
            "NZDUSD": "NZDUSD=X",
            "EURJPY": "EURJPY=X",
            "GBPJPY": "GBPJPY=X",
            "EURGBP": "EURGBP=X",
            "GOLD": "GC=F",
            "SILVER": "SI=F",
        }.get(symbol)

    def resolve_source_symbol(self, symbol: str, provider: Optional[str] = None) -> str:
        root = (provider or "").split("-")[0].strip().lower()
        if root == "yahoo":
            return self._to_yahoo_symbol(symbol) or symbol
        if root == "twelve":
            return self._to_twelve_symbol(symbol)
        if root == "finnhub":
            return self._to_finnhub_symbol(symbol) or symbol
        return symbol

    def source_kind_for(self, symbol: str) -> str:
        if symbol in SETTINGS.assets_pure_crypto:
            return "pure_crypto"
        if symbol in SETTINGS.assets_crypto:
            return "crypto_pair"
        if symbol in SETTINGS.assets_forex:
            return "forex"
        if symbol in SETTINGS.assets_metals:
            return "metals"
        return "unknown"

    def _parse_ts(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            val = float(value)
            return val if val > 0 else None

        text = str(value).strip()
        if not text:
            return None

        try:
            return float(text)
        except Exception:
            pass

        for candidate in (
            text.replace("Z", "+00:00"),
            text.replace(" UTC", "+00:00"),
            text,
        ):
            try:
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).timestamp()
            except Exception:
                continue

        return None

    def build_m5_from_m1(self, candles: List[Candle], outputsize: int = 50) -> List[Candle]:
        if not candles:
            return []

        buckets: Dict[int, Dict[str, float]] = {}
        bucket_order: List[int] = []

        for candle in candles:
            ts = self._parse_ts(getattr(candle, "ts", None))
            if ts is None:
                continue

            bucket_start = int(ts // 300) * 300
            o = float(candle.open)
            h = float(candle.high)
            l = float(candle.low)
            c = float(candle.close)
            v = float(candle.volume or 0.0)

            if bucket_start not in buckets:
                buckets[bucket_start] = {
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                }
                bucket_order.append(bucket_start)
            else:
                row = buckets[bucket_start]
                row["high"] = max(float(row["high"]), h)
                row["low"] = min(float(row["low"]), l)
                row["close"] = c
                row["volume"] = float(row["volume"]) + v

        out: List[Candle] = []
        for bucket_start in sorted(bucket_order)[-max(1, outputsize):]:
            row = buckets[bucket_start]
            out.append(
                Candle(
                    ts=datetime.fromtimestamp(bucket_start, tz=timezone.utc).isoformat(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )

        return out

    def _fetch_binance(self, symbol: str, interval: str, limit: int) -> List[Candle]:
        cached = self._get_cache("binance", symbol, interval)
        if cached:
            self._remember(symbol, "binance-cache")
            return self._trim(cached, limit)

        interval_value = "5m" if interval == "5min" else "1m"
        for url in (
            "https://data-api.binance.vision/api/v3/klines",
            "https://api.binance.com/api/v3/klines",
        ):
            data = self._http_get_json(
                url,
                params={"symbol": symbol, "interval": interval_value, "limit": limit},
                timeout=4,
            )
            if isinstance(data, list):
                candles = self._trim(binance.normalize(data), limit)
                if candles:
                    self._set_cache("binance", symbol, interval, candles)
                    self._remember(symbol, "binance")
                    self.health.mark_success("binance")
                    return candles

        self.health.mark_failure("binance", "request_failed")
        return []

    def _fetch_finnhub(self, symbol: str, interval: str, outputsize: int) -> List[Candle]:
        if not SETTINGS.finnhub_api_key:
            return []

        cached = self._get_cache("finnhub", symbol, interval)
        if cached:
            self._remember(symbol, "finnhub-cache")
            return self._trim(cached, outputsize)

        fh_symbol = self._to_finnhub_symbol(symbol)
        if not fh_symbol:
            return []

        resolution = "5" if interval == "5min" else "1"
        seconds_per_bar = 300 if resolution == "5" else 60
        lookback = max(outputsize, 50) * seconds_per_bar + seconds_per_bar
        to_ts = int(time.time())
        from_ts = to_ts - lookback

        data = self._http_get_json(
            "https://finnhub.io/api/v1/forex/candle",
            params={
                "symbol": fh_symbol,
                "resolution": resolution,
                "from": from_ts,
                "to": to_ts,
                "token": SETTINGS.finnhub_api_key,
            },
            timeout=4,
        )
        candles = self._trim(finnhub.normalize(data or {}), outputsize)
        if candles:
            self._set_cache("finnhub", symbol, interval, candles)
            self._remember(symbol, "finnhub")
            self.health.mark_success("finnhub")
            return candles

        self.health.mark_failure("finnhub", "request_failed")
        return []

    def _reset_daily_if_needed(self) -> None:
        current_day = datetime.now().astimezone().strftime("%Y-%m-%d")
        if current_day != self.day_marker:
            self.day_marker = current_day
            for item in self.key_usage:
                item["daily"] = 0
                item["minute"] = 0
                item["minute_window_start"] = time.time()

    def _choose_twelve_key_index(self) -> Optional[int]:
        self._reset_daily_if_needed()
        now = time.time()
        available = []
        for idx, item in enumerate(self.key_usage):
            if now - float(item["minute_window_start"]) >= 60:
                item["minute"] = 0
                item["minute_window_start"] = now
            if int(item["minute"]) < 1:
                available.append(idx)
        return available[0] if available else None

    def _fetch_twelve(self, symbol: str, interval: str, outputsize: int) -> List[Candle]:
        cached = self._get_cache("twelve", symbol, interval)
        if cached:
            self._remember(symbol, "twelve-cache")
            return self._trim(cached, outputsize)

        idx = self._choose_twelve_key_index()
        if idx is None:
            return []

        data = self._http_get_json(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": self._to_twelve_symbol(symbol),
                "interval": interval,
                "outputsize": outputsize,
                "apikey": self.key_usage[idx]["key"],
            },
            timeout=4,
        )
        if isinstance(data, dict) and "values" in data:
            candles = self._trim(twelve.normalize(data["values"]), outputsize)
            if candles:
                self.key_usage[idx]["daily"] += 1
                self.key_usage[idx]["minute"] += 1
                self._set_cache("twelve", symbol, interval, candles)
                self._remember(symbol, f"twelve-key-{idx+1}")
                self.health.mark_success("twelve")
                return candles

        self.health.mark_failure("twelve", "request_failed")
        return []

    def _fetch_alpha(self, symbol: str, interval: str, outputsize: int) -> List[Candle]:
        if not SETTINGS.alpha_vantage_api_key or len(symbol) != 6:
            return []

        cached = self._get_cache("alpha", symbol, interval)
        if cached:
            self._remember(symbol, "alpha-cache")
            return self._trim(cached, outputsize)

        interval_value = "5min" if interval == "5min" else "1min"
        mode = "full" if outputsize > 100 else "compact"

        data = self._http_get_json(
            "https://www.alphavantage.co/query",
            params={
                "function": "FX_INTRADAY",
                "from_symbol": symbol[:3],
                "to_symbol": symbol[3:],
                "interval": interval_value,
                "outputsize": mode,
                "apikey": SETTINGS.alpha_vantage_api_key,
            },
            timeout=5,
        )
        candles = self._trim(alpha_vantage.normalize(data or {}), outputsize)
        if candles:
            self._set_cache("alpha", symbol, interval, candles)
            self._remember(symbol, "alpha")
            self.health.mark_success("alpha")
            return candles

        self.health.mark_failure("alpha", "request_failed")
        return []

    def _fetch_yahoo(self, symbol: str, interval: str, outputsize: int) -> List[Candle]:
        cached = self._get_cache("yahoo", symbol, interval)
        if cached:
            self._remember(symbol, "yahoo-cache")
            return self._trim(cached, outputsize)

        yahoo_symbol = self._to_yahoo_symbol(symbol)
        if not yahoo_symbol:
            return []

        interval_value = "5m" if interval == "5min" else "1m"
        if interval == "5min":
            range_value = "5d"
        elif outputsize > 390:
            range_value = "5d"
        elif outputsize > 180:
            range_value = "2d"
        else:
            range_value = "1d"

        data = self._http_get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
            params={
                "interval": interval_value,
                "range": range_value,
                "includePrePost": "true",
            },
            timeout=4,
        )
        candles = self._trim(yahoo.normalize(data or {}, limit=outputsize), outputsize)
        if candles:
            self._set_cache("yahoo", symbol, interval, candles)
            self._remember(symbol, "yahoo")
            self.health.mark_success("yahoo")
            return candles

        self.health.mark_failure("yahoo", "request_failed")
        return []

    def get_candles(self, symbol: str, interval: str = "1min", outputsize: int = 50) -> Tuple[List[Candle], List[str]]:
        chain = self.router.provider_chain_for(symbol)
        for provider in chain:
            if provider == "binance":
                candles = self._fetch_binance(symbol, interval, outputsize)
            elif provider == "finnhub":
                candles = self._fetch_finnhub(symbol, interval, outputsize)
            elif provider == "twelve":
                candles = self._fetch_twelve(symbol, interval, outputsize)
            elif provider == "alpha":
                candles = self._fetch_alpha(symbol, interval, outputsize)
            else:
                candles = self._fetch_yahoo(symbol, interval, outputsize)

            if candles:
                return candles, chain

        return [], chain
