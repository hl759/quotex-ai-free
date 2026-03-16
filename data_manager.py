import time
import requests
from datetime import datetime
from config import (
    TWELVE_API_KEYS, FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY,
    TWELVE_DAILY_SOFT_LIMIT_PER_KEY, TWELVE_MINUTE_LIMIT_PER_KEY, TWELVE_GLOBAL_DAILY_HARD_STOP,
    CACHE_TTL_1MIN, CACHE_TTL_5MIN, ECONOMY_MODE_AFTER_TOTAL, FREEZE_TWELVE_AFTER_TOTAL,
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
        self.finnhub_frozen_for_day = False
        self.finnhub_pause_until_ts = 0
        self.alpha_frozen_for_day = False
        self.alpha_pause_until_ts = 0
        self.key_usage = [{"key": k, "daily": 0, "minute": 0, "minute_window_start": time.time()} for k in TWELVE_API_KEYS]

    def _reset_daily_if_needed(self):
        current_day = datetime.utcnow().strftime("%Y-%m-%d")
        if current_day != self.day_marker:
            self.day_marker = current_day
            self.credits_today = 0
            self.twelve_frozen_for_day = False
            self.twelve_pause_until_ts = 0
            self.finnhub_frozen_for_day = False
            self.finnhub_pause_until_ts = 0
            self.alpha_frozen_for_day = False
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

    def _get_cache_ttl(self, interval):
        return CACHE_TTL_5MIN if interval == "5min" else CACHE_TTL_1MIN

    def _cache_key(self, provider, symbol, interval):
        return f"{provider}:{symbol}:{interval}"

    def _get_from_cache(self, provider, symbol, interval):
        item = self.cache.get(self._cache_key(provider, symbol, interval))
        if not item or time.time() > item["expires_at"]:
            return None
        return item["data"]

    def _set_cache(self, provider, symbol, interval, data):
        self.cache[self._cache_key(provider, symbol, interval)] = {
            "data": data,
            "expires_at": time.time() + self._get_cache_ttl(interval)
        }

    def _to_twelve_symbol(self, symbol):
        return {
            "EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY","AUDUSD":"AUD/USD","USDCAD":"USD/CAD",
            "USDCHF":"USD/CHF","NZDUSD":"NZD/USD","EURJPY":"EUR/JPY","GBPJPY":"GBP/JPY","EURGBP":"EUR/GBP",
            "GOLD":"XAU/USD","SILVER":"XAG/USD",
        }.get(symbol, symbol)

    def _to_finnhub_symbol(self, symbol):
        return {
            "EURUSD":"OANDA:EUR_USD","GBPUSD":"OANDA:GBP_USD","USDJPY":"OANDA:USD_JPY","AUDUSD":"OANDA:AUD_USD",
            "USDCAD":"OANDA:USD_CAD","USDCHF":"OANDA:USD_CHF","NZDUSD":"OANDA:NZD_USD",
            "EURJPY":"OANDA:EUR_JPY","GBPJPY":"OANDA:GBP_JPY","EURGBP":"OANDA:EUR_GBP",
        }.get(symbol)

    def _choose_twelve_key_index(self):
        self._reset_daily_if_needed()
        self._reset_minute_windows_if_needed()
        if self.twelve_frozen_for_day or time.time() < self.twelve_pause_until_ts or self.credits_today >= FREEZE_TWELVE_AFTER_TOTAL:
            self.twelve_frozen_for_day = self.credits_today >= FREEZE_TWELVE_AFTER_TOTAL or self.twelve_frozen_for_day
            return None
        available = [i for i, item in enumerate(self.key_usage) if item["daily"] < TWELVE_DAILY_SOFT_LIMIT_PER_KEY and item["minute"] < TWELVE_MINUTE_LIMIT_PER_KEY]
        if not available:
            return None
        available.sort(key=lambda idx: self.key_usage[idx]["daily"])
        return available[0]

    def _consume_twelve_credit(self, key_index):
        self.key_usage[key_index]["daily"] += 1
        self.key_usage[key_index]["minute"] += 1
        self.credits_today += 1

    def _normalize_twelve_values(self, values):
        return [{"datetime": r.get("datetime"), "open": r.get("open"), "high": r.get("high"), "low": r.get("low"), "close": r.get("close"), "volume": r.get("volume", "0")} for r in values]

    def _normalize_binance_klines(self, klines):
        out = []
        for item in klines:
            out.append({"datetime": datetime.utcfromtimestamp(item[0] / 1000).strftime("%Y-%m-%d %H:%M:%S"), "open": str(item[1]), "high": str(item[2]), "low": str(item[3]), "close": str(item[4]), "volume": str(item[5])})
        out.reverse()
        return out

    def _normalize_finnhub(self, data):
        if not data.get("c") or data.get("s") != "ok":
            return None
        out = []
        for i in range(len(data["c"])):
            out.append({
                "datetime": datetime.utcfromtimestamp(data["t"][i]).strftime("%Y-%m-%d %H:%M:%S"),
                "open": str(data["o"][i]), "high": str(data["h"][i]), "low": str(data["l"][i]),
                "close": str(data["c"][i]), "volume": str(data["v"][i] if i < len(data["v"]) else 0)
            })
        out.reverse()
        return out

    def _normalize_alpha_fx(self, data):
        ts = data.get("Time Series FX (1min)", {})
        if not ts:
            return None
        out = []
        for dt_str, row in ts.items():
            out.append({"datetime": dt_str, "open": row.get("1. open"), "high": row.get("2. high"), "low": row.get("3. low"), "close": row.get("4. close"), "volume": "0"})
        return out[:50]

    def _fetch_binance(self, symbol, interval="1min", limit=50):
        cached = self._get_from_cache("binance", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "binance-cache"
            return cached
        url = "https://data-api.binance.vision/api/v3/klines"
        params = {"symbol": symbol, "interval": "5m" if interval == "5min" else "1m", "limit": limit}
        try:
            data = requests.get(url, params=params, timeout=10).json()
            if not isinstance(data, list):
                return None
            candles = self._normalize_binance_klines(data)
            self._set_cache("binance", symbol, interval, candles)
            self.last_provider_used[symbol] = "binance"
            return candles
        except Exception as e:
            print(f"Binance error for {symbol}: {e}", flush=True)
            return None

    def _handle_twelve_error_response(self, symbol, data):
        code = data.get("code")
        message = str(data.get("message", "")).lower()
        print(f"Twelve invalid response for {symbol}: {data}", flush=True)
        if code == 429 and ("for the day" in message or "run out of api credits for the day" in message):
            self.twelve_frozen_for_day = True
        elif code == 429:
            self.twelve_pause_until_ts = time.time() + 65
        return None

    def _fetch_twelve(self, symbol, interval="1min", outputsize=50):
        cached = self._get_from_cache("twelve", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "twelve-cache"
            return cached
        self._reset_daily_if_needed()
        self._reset_minute_windows_if_needed()
        if self.twelve_frozen_for_day or time.time() < self.twelve_pause_until_ts or self.credits_today >= TWELVE_GLOBAL_DAILY_HARD_STOP:
            self.twelve_frozen_for_day = self.credits_today >= TWELVE_GLOBAL_DAILY_HARD_STOP or self.twelve_frozen_for_day
            return None
        idx = self._choose_twelve_key_index()
        if idx is None:
            return None
        try:
            params = {"symbol": self._to_twelve_symbol(symbol), "interval": interval, "outputsize": outputsize, "apikey": self.key_usage[idx]["key"]}
            data = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10).json()
            if "values" not in data:
                return self._handle_twelve_error_response(symbol, data)
            candles = self._normalize_twelve_values(data["values"])
            self._set_cache("twelve", symbol, interval, candles)
            self._consume_twelve_credit(idx)
            self.last_provider_used[symbol] = f"twelve-key-{idx + 1}"
            return candles
        except Exception as e:
            print(f"Twelve error for {symbol}: {e}", flush=True)
            self.twelve_pause_until_ts = time.time() + 30
            return None

    def _fetch_finnhub(self, symbol, interval="1min"):
        cached = self._get_from_cache("finnhub", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "finnhub-cache"
            return cached
        if not FINNHUB_API_KEY or self.finnhub_frozen_for_day or time.time() < self.finnhub_pause_until_ts:
            return None
        finnhub_symbol = self._to_finnhub_symbol(symbol)
        if not finnhub_symbol:
            return None
        try:
            to_ts = int(time.time())
            params = {"symbol": finnhub_symbol, "resolution": "1", "from": to_ts - 60 * 50, "to": to_ts, "token": FINNHUB_API_KEY}
            data = requests.get("https://finnhub.io/api/v1/forex/candle", params=params, timeout=10).json()
            if data.get("error"):
                msg = str(data.get("error", "")).lower()
                if "limit" in msg or "rate" in msg:
                    self.finnhub_pause_until_ts = time.time() + FINNHUB_PAUSE_SECONDS
                return None
            candles = self._normalize_finnhub(data)
            if not candles:
                return None
            self._set_cache("finnhub", symbol, interval, candles)
            self.last_provider_used[symbol] = "finnhub"
            return candles
        except Exception as e:
            print(f"Finnhub error for {symbol}: {e}", flush=True)
            self.finnhub_pause_until_ts = time.time() + FINNHUB_PAUSE_SECONDS
            return None

    def _fetch_alpha(self, symbol, interval="1min"):
        cached = self._get_from_cache("alpha", symbol, interval)
        if cached:
            self.last_provider_used[symbol] = "alpha-cache"
            return cached
        if not ALPHA_VANTAGE_API_KEY or self.alpha_frozen_for_day or time.time() < self.alpha_pause_until_ts or len(symbol) != 6:
            return None
        try:
            params = {"function": "FX_INTRADAY", "from_symbol": symbol[:3], "to_symbol": symbol[3:], "interval": "1min", "outputsize": "compact", "apikey": ALPHA_VANTAGE_API_KEY}
            data = requests.get("https://www.alphavantage.co/query", params=params, timeout=12).json()
            if "Note" in data or "Information" in data:
                self.alpha_pause_until_ts = time.time() + ALPHA_PAUSE_SECONDS
                return None
            candles = self._normalize_alpha_fx(data)
            if not candles:
                return None
            self._set_cache("alpha", symbol, interval, candles)
            self.last_provider_used[symbol] = "alpha"
            return candles
        except Exception as e:
            print(f"Alpha error for {symbol}: {e}", flush=True)
            self.alpha_pause_until_ts = time.time() + ALPHA_PAUSE_SECONDS
            return None

    def get_candles(self, symbol, interval="1min", outputsize=50):
        self._reset_daily_if_needed()
        if self._is_crypto(symbol):
            return self._fetch_binance(symbol, interval=interval, limit=outputsize)
        candles = self._fetch_finnhub(symbol, interval=interval)
        if candles:
            return candles
        candles = self._fetch_twelve(symbol, interval=interval, outputsize=30 if self.credits_today >= ECONOMY_MODE_AFTER_TOTAL else outputsize)
        if candles:
            return candles
        return self._fetch_alpha(symbol, interval=interval)

    def get_usage_snapshot(self):
        return {
            "credits_today_total": self.credits_today,
            "economy_mode": self.credits_today >= ECONOMY_MODE_AFTER_TOTAL,
            "twelve_frozen": self.twelve_frozen_for_day,
            "twelve_minute_paused": time.time() < self.twelve_pause_until_ts,
            "finnhub_frozen": self.finnhub_frozen_for_day,
            "alpha_frozen": self.alpha_frozen_for_day,
            "global_hard_stop": TWELVE_GLOBAL_DAILY_HARD_STOP,
            "keys": [{"key_number": i + 1, "daily_used": item["daily"], "minute_used": item["minute"]} for i, item in enumerate(self.key_usage)]
        }
