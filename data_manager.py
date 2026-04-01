import time
import requests
from datetime import datetime
from config import (
    TWELVE_API_KEYS, FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY,
    TWELVE_DAILY_SOFT_LIMIT_PER_KEY, TWELVE_MINUTE_LIMIT_PER_KEY,
    TWELVE_GLOBAL_DAILY_HARD_STOP, CACHE_TTL_1MIN, CACHE_TTL_5MIN,
    ECONOMY_MODE_AFTER_TOTAL, FREEZE_TWELVE_AFTER_TOTAL,
    FINNHUB_PAUSE_SECONDS, ALPHA_PAUSE_SECONDS,
)


class DataManager:
    def __init__(self):
        self.cache = {}
        self.day_marker = datetime.utcnow().strftime("%Y-%m-%d")
        self.credits_today = 0
        self.last_provider_used = {}

        self.twelve_frozen_for_day = False
        self.twelve_pause_until_ts = 0
        self.finnhub_pause_until_ts = 0
        self.alpha_pause_until_ts = 0

        self.key_usage = [{"key": key, "daily": 0, "minute": 0, "minute_window_start": time.time()} for key in TWELVE_API_KEYS]

    def _reset_daily_if_needed(self):
        current_day = datetime.utcnow().strftime("%Y-%m-%d")
        if current_day != self.day_marker:
            self.day_marker = current_day
            self.credits_today = 0
            self.twelve_frozen_for_day = False
            self.twelve_pause_until_ts = 0
            self.finnhub_pause_until_ts = 0
            self.alpha_pause_until_ts = 0
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

    def _ttl(self, interval):
        return CACHE_TTL_5MIN if interval == "5min" else CACHE_TTL_1MIN

    def _cache_key(self, provider, symbol, interval):
        return f"{provider}:{symbol}:{interval}"

    def _get_cache(self, provider, symbol, interval):
        item = self.cache.get(self._cache_key(provider, symbol, interval))
        if not item or time.time() > item["expires_at"]:
            return None
        return item["data"]

    def _set_cache(self, provider, symbol, interval, data):
        self.cache[self._cache_key(provider, symbol, interval)] = {
            "data": data,
            "expires_at": time.time() + self._ttl(interval)
        }

    def _to_twelve_symbol(self, symbol):
        return {
            "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
            "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
            "NZDUSD": "NZD/USD", "EURJPY": "EUR/JPY", "GBPJPY": "GBP/JPY",
            "EURGBP": "EUR/GBP", "GOLD": "XAU/USD", "SILVER": "XAG/USD"
        }.get(symbol, symbol)

    def _to_finnhub_symbol(self, symbol):
        return {
            "EURUSD": "OANDA:EUR_USD", "GBPUSD": "OANDA:GBP_USD", "USDJPY": "OANDA:USD_JPY",
            "AUDUSD": "OANDA:AUD_USD", "USDCAD": "OANDA:USD_CAD", "USDCHF": "OANDA:USD_CHF",
            "NZDUSD": "OANDA:NZD_USD", "EURJPY": "OANDA:EUR_JPY", "GBPJPY": "OANDA:GBP_JPY",
            "EURGBP": "OANDA:EUR_GBP"
        }.get(symbol)

    def _choose_twelve_key_index(self):
        self._reset_daily_if_needed()
        self._reset_minute_windows_if_needed()

        if self.twelve_frozen_for_day or time.time() < self.twelve_pause_until_ts or self.credits_today >= FREEZE_TWELVE_AFTER_TOTAL:
            self.twelve_frozen_for_day = self.credits_today >= FREEZE_TWELVE_AFTER_TOTAL
            return None

        available = [i for i, item in enumerate(self.key_usage) if item["daily"] < TWELVE_DAILY_SOFT_LIMIT_PER_KEY and item["minute"] < TWELVE_MINUTE_LIMIT_PER_KEY]
        if not available:
            return None

        available.sort(key=lambda idx: self.key_usage[idx]["daily"])
        return available[0]

    def _consume_twelve(self, idx):
        self.key_usage[idx]["daily"] += 1
        self.key_usage[idx]["minute"] += 1
        self.credits_today += 1

    def _normalize_twelve(self, values):
        return [{"datetime": row.get("datetime"), "open": row.get("open"), "high": row.get("high"), "low": row.get("low"), "close": row.get("close"), "volume": row.get("volume", "0")} for row in values]

    def _normalize_binance(self, rows):
        out = []
        for row in rows:
            out.append({
                "datetime": datetime.utcfromtimestamp(row[0] / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                "open": str(row[1]),
                "high": str(row[2]),
                "low": str(row[3]),
                "close": str(row[4]),
                "volume": str(row[5]),
            })
        out.reverse()
        return out

    def _normalize_finnhub(self, data):
        if data.get("s") != "ok" or not data.get("c"):
            return None
        out = []
        for i in range(len(data["c"])):
            out.append({
                "datetime": datetime.utcfromtimestamp(data["t"][i]).strftime("%Y-%m-%d %H:%M:%S"),
                "open": str(data["o"][i]),
                "high": str(data["h"][i]),
                "low": str(data["l"][i]),
                "close": str(data["c"][i]),
                "volume": str(data["v"][i] if i < len(data["v"]) else 0),
            })
        out.reverse()
        return out

    def _normalize_alpha(self, data):
        ts = data.get("Time Series FX (1min)", {})
        if not ts:
            return None
        out = []
        for dt_str, row in list(ts.items())[:50]:
            out.append({
                "datetime": dt_str,
                "open": row.get("1. open"),
                "high": row.get("2. high"),
                "low": row.get("3. low"),
                "close": row.get("4. close"),
                "volume": "0",
            })
        return out

    def _fetch_binance(self, symbol, interval="1min", limit=50):
        cached = self._get_cache("binance", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "binance-cache"
            return cached
        try:
            r = requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol": symbol, "interval": "5m" if interval == "5min" else "1m", "limit": limit}, timeout=10)
            data = r.json()
            if not isinstance(data, list):
                return None
            candles = self._normalize_binance(data)
            self._set_cache("binance", symbol, interval, candles)
            self.last_provider_used[symbol] = "binance"
            return candles
        except Exception:
            return None

    def _fetch_finnhub(self, symbol, interval="1min"):
        cached = self._get_cache("finnhub", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "finnhub-cache"
            return cached

        if not FINNHUB_API_KEY or time.time() < self.finnhub_pause_until_ts:
            return None

        fh_symbol = self._to_finnhub_symbol(symbol)
        if not fh_symbol:
            return None

        try:
            to_ts = int(time.time())
            from_ts = to_ts - 60 * 50
            r = requests.get("https://finnhub.io/api/v1/forex/candle", params={"symbol": fh_symbol, "resolution": "1", "from": from_ts, "to": to_ts, "token": FINNHUB_API_KEY}, timeout=10)
            data = r.json()
            if data.get("error"):
                self.finnhub_pause_until_ts = time.time() + FINNHUB_PAUSE_SECONDS
                return None
            candles = self._normalize_finnhub(data)
            if not candles:
                return None
            self._set_cache("finnhub", symbol, interval, candles)
            self.last_provider_used[symbol] = "finnhub"
            return candles
        except Exception:
            self.finnhub_pause_until_ts = time.time() + FINNHUB_PAUSE_SECONDS
            return None

    def _fetch_twelve(self, symbol, interval="1min", outputsize=50):
        cached = self._get_cache("twelve", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "twelve-cache"
            return cached

        self._reset_daily_if_needed()
        self._reset_minute_windows_if_needed()
        if self.twelve_frozen_for_day or time.time() < self.twelve_pause_until_ts or self.credits_today >= TWELVE_GLOBAL_DAILY_HARD_STOP:
            self.twelve_frozen_for_day = self.credits_today >= TWELVE_GLOBAL_DAILY_HARD_STOP
            return None

        idx = self._choose_twelve_key_index()
        if idx is None:
            return None

        try:
            r = requests.get("https://api.twelvedata.com/time_series", params={"symbol": self._to_twelve_symbol(symbol), "interval": interval, "outputsize": outputsize, "apikey": self.key_usage[idx]["key"]}, timeout=10)
            data = r.json()
            if "values" not in data:
                msg = str(data.get("message", "")).lower()
                if data.get("code") == 429 and "for the day" in msg:
                    self.twelve_frozen_for_day = True
                elif data.get("code") == 429:
                    self.twelve_pause_until_ts = time.time() + 65
                return None
            candles = self._normalize_twelve(data["values"])
            self._set_cache("twelve", symbol, interval, candles)
            self._consume_twelve(idx)
            self.last_provider_used[symbol] = f"twelve-key-{idx + 1}"
            return candles
        except Exception:
            self.twelve_pause_until_ts = time.time() + 30
            return None

    def _fetch_alpha(self, symbol, interval="1min"):
        cached = self._get_cache("alpha", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "alpha-cache"
            return cached

        if not ALPHA_VANTAGE_API_KEY or time.time() < self.alpha_pause_until_ts or len(symbol) != 6:
            return None

        try:
            r = requests.get("https://www.alphavantage.co/query", params={"function": "FX_INTRADAY", "from_symbol": symbol[:3], "to_symbol": symbol[3:], "interval": "1min", "outputsize": "compact", "apikey": ALPHA_VANTAGE_API_KEY}, timeout=12)
            data = r.json()
            if "Note" in data or "Information" in data:
                self.alpha_pause_until_ts = time.time() + ALPHA_PAUSE_SECONDS
                return None
            candles = self._normalize_alpha(data)
            if not candles:
                return None
            self._set_cache("alpha", symbol, interval, candles)
            self.last_provider_used[symbol] = "alpha"
            return candles
        except Exception:
            self.alpha_pause_until_ts = time.time() + ALPHA_PAUSE_SECONDS
            return None

    def get_candles(self, symbol, interval="1min", outputsize=50):
        self._reset_daily_if_needed()

        if self._is_crypto(symbol):
            return self._fetch_binance(symbol, interval=interval, limit=outputsize)

        # Para M5 real de Forex — vai direto para Twelve Data (mais confiável)
        if interval == "5min":
            candles = self._fetch_twelve(symbol, interval="5min", outputsize=outputsize)
            if candles:
                return candles
            return None

        # Para M1 de Forex — cascata normal
        candles = self._fetch_finnhub(symbol, interval=interval)
        if candles:
            return candles

        candles = self._fetch_twelve(symbol, interval=interval, outputsize=30 if self.credits_today >= ECONOMY_MODE_AFTER_TOTAL else outputsize)
        if candles:
            return candles

        return self._fetch_alpha(symbol, interval=interval)
