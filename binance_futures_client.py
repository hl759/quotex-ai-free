
import hashlib
import hmac
import os
import threading
import time
from urllib.parse import urlencode

import requests

from core.security import sanitize_error


class BinanceFuturesClient:
    def __init__(self, vault, logger=None):
        self.vault = vault
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AlphaHivePlatform/2.0"})
        self._lock = threading.Lock()
        self._last_request_ts = 0.0
        self.min_request_gap = float(os.getenv("BINANCE_MIN_REQUEST_GAP_SECONDS", "0.12") or 0.12)
        self.base_url_live = os.getenv("BINANCE_FUTURES_BASE_URL", "https://fapi.binance.com").strip() or "https://fapi.binance.com"
        self.base_url_testnet = os.getenv("BINANCE_FUTURES_TESTNET_URL", "https://testnet.binancefuture.com").strip() or "https://testnet.binancefuture.com"
        self.recv_window = int(float(os.getenv("BINANCE_RECV_WINDOW", "5000") or 5000))
        self.timeout = float(os.getenv("BINANCE_HTTP_TIMEOUT_SECONDS", "10") or 10)
        self.max_retries = int(float(os.getenv("BINANCE_HTTP_MAX_RETRIES", "3") or 3))

    def _log(self, message, level="info"):
        if not self.logger:
            return
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)

    def _base_url(self):
        return self.base_url_testnet if self.vault.is_testnet() else self.base_url_live

    def _credentials(self):
        api_key, api_secret = self.vault.credentials()
        if not api_key or not api_secret:
            raise ValueError("binance_credentials_not_connected")
        return api_key, api_secret

    def _signed_params(self, params):
        api_key, api_secret = self._credentials()
        payload = dict(params or {})
        payload.setdefault("recvWindow", self.recv_window)
        payload["timestamp"] = int(time.time() * 1000)
        query = urlencode(payload, doseq=True)
        signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        return api_key, f"{query}&signature={signature}"

    def _throttle(self):
        with self._lock:
            now = time.time()
            wait = self.min_request_gap - (now - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.time()

    def _request(self, method, path, params=None, signed=False):
        self._throttle()
        url = f"{self._base_url()}{path}"
        headers = {}
        kwargs = {"timeout": self.timeout}

        if signed:
            api_key, query = self._signed_params(params)
            headers["X-MBX-APIKEY"] = api_key
            if method.upper() in ("GET", "DELETE"):
                url = f"{url}?{query}"
            else:
                kwargs["data"] = query
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            if params:
                kwargs["params"] = params

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(method=method.upper(), url=url, headers=headers, **kwargs)
                if response.status_code in (418, 429):
                    retry_after = float(response.headers.get("Retry-After", "1") or 1)
                    time.sleep(min(5.0, max(1.0, retry_after)))
                    last_error = RuntimeError(f"binance_rate_limit_{response.status_code}")
                    continue
                if response.status_code >= 500:
                    time.sleep(min(4.0, 0.6 * attempt))
                    last_error = RuntimeError(f"binance_server_error_{response.status_code}")
                    continue
                payload = response.json()
                if response.status_code >= 400:
                    raise RuntimeError(f"binance_error_{response.status_code}:{payload}")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(3.0, 0.5 * attempt))
                    continue
        raise RuntimeError(sanitize_error(last_error))

    def ping(self):
        try:
            self._request("GET", "/fapi/v1/ping", signed=False)
            return {"ok": True, "base_url": self._base_url()}
        except Exception as exc:
            return {"ok": False, "error": sanitize_error(exc), "base_url": self._base_url()}

    def account_balance(self):
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def account_info(self):
        return self._request("GET", "/fapi/v2/account", signed=True)

    def position_risk(self, symbol=None):
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v3/positionRisk", params=params, signed=True)

    def open_orders(self, symbol=None):
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    def order_history(self, symbol, limit=50):
        params = {"symbol": symbol, "limit": max(1, min(100, int(limit or 50)))}
        return self._request("GET", "/fapi/v1/allOrders", params=params, signed=True)

    def change_leverage(self, symbol, leverage):
        params = {"symbol": symbol, "leverage": int(leverage)}
        return self._request("POST", "/fapi/v1/leverage", params=params, signed=True)

    def new_order(self, **params):
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)

    def cancel_order(self, symbol, order_id):
        return self._request("DELETE", "/fapi/v1/order", params={"symbol": symbol, "orderId": order_id}, signed=True)

    def cancel_all_orders(self, symbol):
        return self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol}, signed=True)
