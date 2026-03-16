import time
import requests
from datetime import datetime
from config import (
    TWELVE_API_KEYS,
    TWELVE_DAILY_SOFT_LIMIT_PER_KEY,
    TWELVE_MINUTE_LIMIT_PER_KEY,
    TWELVE_GLOBAL_DAILY_HARD_STOP,
    CACHE_TTL_1MIN,
    CACHE_TTL_5MIN,
    ECONOMY_MODE_AFTER_TOTAL,
    FREEZE_TWELVE_AFTER_TOTAL,
)

class DataManager:
    def __init__(self):
        self.cache = {}
        self.day_marker = datetime.utcnow().strftime("%Y-%m-%d")
        self.credits_today = 0
        self.last_provider_used = {}

        self.key_usage = []
        for key in TWELVE_API_KEYS:
            self.key_usage.append({
                "key": key,
                "daily": 0,
                "minute": 0,
                "minute_window_start": time.time()
            })

    def _reset_daily_if_needed(self):
        current_day = datetime.utcnow().strftime("%Y-%m-%d")
        if current_day != self.day_marker:
            self.day_marker = current_day
            self.credits_today = 0
            for item in self.key_usage:
                item["daily"] = 0
                item["minute"] = 0
                item["minute_window_start"] = time.time()

    def _reset_minute_windows_if_needed(self):
        now = time.time()
        for item in self.key_usage:
            if now - item["minute_window_start"] >= 60:
                item["minute"] = 0
                item["minute_window_start"] = now

    def _is_crypto(self, symbol):
        return symbol.endswith(("USDT", "BUSD", "BTC", "ETH", "BNB"))

    def _get_cache_ttl(self, interval):
        return CACHE_TTL_5MIN if interval == "5min" else CACHE_TTL_1MIN

    def _cache_key(self, provider, symbol, interval):
        return f"{provider}:{symbol}:{interval}"

    def _get_from_cache(self, provider, symbol, interval):
        key = self._cache_key(provider, symbol, interval)
        item = self.cache.get(key)
        if not item:
            return None
        if time.time() > item["expires_at"]:
            return None
        return item["data"]

    def _set_cache(self, provider, symbol, interval, data):
        key = self._cache_key(provider, symbol, interval)
        self.cache[key] = {
            "data": data,
            "expires_at": time.time() + self._get_cache_ttl(interval)
        }

    def _choose_twelve_key_index(self):
        self._reset_daily_if_needed()
        self._reset_minute_windows_if_needed()

        if self.credits_today >= FREEZE_TWELVE_AFTER_TOTAL:
            return None

        available = []
        for i, item in enumerate(self.key_usage):
            if item["daily"] < TWELVE_DAILY_SOFT_LIMIT_PER_KEY and item["minute"] < TWELVE_MINUTE_LIMIT_PER_KEY:
                available.append(i)

        if not available:
            return None

        available.sort(key=lambda idx: self.key_usage[idx]["daily"])
        return available[0]

    def _consume_twelve_credit(self, key_index):
        self.key_usage[key_index]["daily"] += 1
        self.key_usage[key_index]["minute"] += 1
        self.credits_today += 1

    def _normalize_twelve_values(self, values):
        out = []
        for row in values:
            out.append({
                "datetime": row.get("datetime"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume", "0")
            })
        return out

    def _normalize_binance_klines(self, klines):
        out = []
        for item in klines:
            out.append({
                "datetime": datetime.utcfromtimestamp(item[0] / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                "open": str(item[1]),
                "high": str(item[2]),
                "low": str(item[3]),
                "close": str(item[4]),
                "volume": str(item[5]),
            })
        out.reverse()
        return out

    def _to_twelve_symbol(self, symbol):
        forex_map = {
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
        }
        return forex_map.get(symbol, symbol)

    def _fetch_binance(self, symbol, interval="1min", limit=50):
        cached = self._get_from_cache("binance", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "binance-cache"
            return cached

        binance_interval = "5m" if interval == "5min" else "1m"
        url = "https://data-api.binance.vision/api/v3/klines"
        params = {"symbol": symbol, "interval": binance_interval, "limit": limit}

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if not isinstance(data, list):
                return None

            candles = self._normalize_binance_klines(data)
            self._set_cache("binance", symbol, interval, candles)
            self.last_provider_used[symbol] = "binance"
            return candles
        except Exception as e:
            print(f"Binance error for {symbol}: {e}", flush=True)
            return None

    def _fetch_twelve(self, symbol, interval="1min", outputsize=50):
        cached = self._get_from_cache("twelve", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "twelve-cache"
            return cached

        self._reset_daily_if_needed()
        self._reset_minute_windows_if_needed()

        if self.credits_today >= TWELVE_GLOBAL_DAILY_HARD_STOP:
            print("Twelve hard stop reached", flush=True)
            return None

        key_index = self._choose_twelve_key_index()
        if key_index is None:
            print("No Twelve key available now", flush=True)
            return None

        key = self.key_usage[key_index]["key"]
        twelve_symbol = self._to_twelve_symbol(symbol)

        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": twelve_symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": key
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if "values" not in data:
                print(f"Twelve invalid response for {symbol} ({twelve_symbol}): {data}", flush=True)
                return None

            candles = self._normalize_twelve_values(data["values"])
            self._set_cache("twelve", symbol, interval, candles)
            self._consume_twelve_credit(key_index)
            self.last_provider_used[symbol] = f"twelve-key-{key_index + 1}"
            return candles
        except Exception as e:
            print(f"Twelve error for {symbol}: {e}", flush=True)
            return None

    def get_candles(self, symbol, interval="1min", outputsize=50):
        self._reset_daily_if_needed()

        # crypto nunca usa fallback na Twelve
        if self._is_crypto(symbol):
            return self._fetch_binance(symbol, interval=interval, limit=outputsize)

        # modo econômico / congelamento
        if self.credits_today >= ECONOMY_MODE_AFTER_TOTAL:
            return self._fetch_twelve(symbol, interval=interval, outputsize=30)

        return self._fetch_twelve(symbol, interval=interval, outputsize=outputsize)

    def get_usage_snapshot(self):
        return {
            "credits_today_total": self.credits_today,
            "economy_mode": self.credits_today >= ECONOMY_MODE_AFTER_TOTAL,
            "frozen_twelve": self.credits_today >= FREEZE_TWELVE_AFTER_TOTAL,
            "global_hard_stop": TWELVE_GLOBAL_DAILY_HARD_STOP,
            "keys": [
                {
                    "key_number": i + 1,
                    "daily_used": item["daily"],
                    "minute_used": item["minute"]
                }
                for i, item in enumerate(self.key_usage)
            ]
        }
