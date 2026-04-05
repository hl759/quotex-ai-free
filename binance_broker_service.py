import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests


class BinanceBrokerService:
    def __init__(self, vault, timeout=12, max_retries=2):
        self.vault = vault
        self.timeout = int(timeout)
        self.max_retries = int(max_retries)

    def _base_url(self):
        state = self.vault.resolve()
        if state.get("testnet"):
            return "https://testnet.binancefuture.com"
        return "https://fapi.binance.com"

    def _headers(self):
        state = self.vault.resolve()
        return {"X-MBX-APIKEY": state.get("api_key", "")}

    def _signed_query(self, params):
        state = self.vault.resolve()
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            str(state.get("api_secret") or "").encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={signature}"

    def _request(self, method, path, signed=False, params=None):
        state = self.vault.resolve()
        if not state.get("api_key") or not state.get("api_secret"):
            return {"ok": False, "error": "missing_credentials", "status": 400}

        params = dict(params or {})
        url = f"{self._base_url()}{path}"
        headers = self._headers()
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                if signed:
                    params["timestamp"] = int(time.time() * 1000)
                    query = self._signed_query(params)
                    target = f"{url}?{query}"
                    response = requests.request(method.upper(), target, headers=headers, timeout=self.timeout)
                else:
                    response = requests.request(method.upper(), url, headers=headers, params=params, timeout=self.timeout)

                try:
                    data = response.json()
                except Exception:
                    data = {"raw": response.text}

                if 200 <= response.status_code < 300:
                    return {"ok": True, "data": data, "status": response.status_code}

                last_error = {"ok": False, "error": data, "status": response.status_code}
                if response.status_code in (418, 429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(0.7 * (attempt + 1))
                    continue
                return last_error
            except Exception as exc:
                last_error = {"ok": False, "error": str(exc), "status": 500}
                if attempt < self.max_retries:
                    time.sleep(0.7 * (attempt + 1))
                    continue
                return last_error
        return last_error or {"ok": False, "error": "unknown_error", "status": 500}

    def ping(self):
        state = self.vault.status()
        if not state.get("connected"):
            return {"ok": False, "connected": False, "vault": state, "error": "missing_credentials"}
        server = self._request("GET", "/fapi/v1/time", signed=False)
        return {
            "ok": bool(server.get("ok")),
            "connected": bool(server.get("ok")),
            "vault": state,
            "server": server,
        }

    def account_overview(self):
        result = self._request("GET", "/fapi/v2/account", signed=True)
        if not result.get("ok"):
            return result
        data = result.get("data") or {}
        assets = data.get("assets") or []
        usdt = next((x for x in assets if str(x.get("asset")) == "USDT"), {})
        return {
            "ok": True,
            "status": result.get("status", 200),
            "summary": {
                "total_wallet_balance": float(usdt.get("walletBalance") or 0.0),
                "available_balance": float(usdt.get("availableBalance") or 0.0),
                "cross_un_pnl": float(usdt.get("crossUnPnl") or 0.0),
                "total_unrealized_profit": float(data.get("totalUnrealizedProfit") or 0.0),
                "total_initial_margin": float(data.get("totalInitialMargin") or 0.0),
                "total_maint_margin": float(data.get("totalMaintMargin") or 0.0),
            },
            "raw": data,
        }

    def positions(self):
        result = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        if not result.get("ok"):
            return result
        rows = []
        for pos in result.get("data") or []:
            amt = float(pos.get("positionAmt") or 0.0)
            if abs(amt) <= 0:
                continue
            rows.append({
                "symbol": pos.get("symbol"),
                "side": "LONG" if amt > 0 else "SHORT",
                "position_amt": amt,
                "entry_price": float(pos.get("entryPrice") or 0.0),
                "mark_price": float(pos.get("markPrice") or 0.0),
                "unrealized_pnl": float(pos.get("unRealizedProfit") or 0.0),
                "liquidation_price": float(pos.get("liquidationPrice") or 0.0),
                "leverage": int(float(pos.get("leverage") or 0)),
                "margin_type": pos.get("marginType"),
            })
        return {"ok": True, "positions": rows, "status": result.get("status", 200)}

    def open_orders(self, symbol=None):
        params = {}
        if symbol:
            params["symbol"] = str(symbol).upper().strip()
        result = self._request("GET", "/fapi/v1/openOrders", signed=True, params=params)
        if not result.get("ok"):
            return result
        rows = []
        for order in result.get("data") or []:
            rows.append({
                "symbol": order.get("symbol"),
                "side": order.get("side"),
                "type": order.get("type"),
                "status": order.get("status"),
                "orig_qty": float(order.get("origQty") or 0.0),
                "price": float(order.get("price") or 0.0),
                "stop_price": float(order.get("stopPrice") or 0.0),
                "reduce_only": bool(order.get("reduceOnly")),
                "time": int(order.get("time") or 0),
            })
        return {"ok": True, "orders": rows, "status": result.get("status", 200)}

    def set_leverage(self, symbol, leverage):
        return self._request(
            "POST",
            "/fapi/v1/leverage",
            signed=True,
            params={"symbol": str(symbol).upper().strip(), "leverage": int(leverage)},
        )

    def cancel_all_orders(self, symbol):
        return self._request(
            "DELETE",
            "/fapi/v1/allOpenOrders",
            signed=True,
            params={"symbol": str(symbol).upper().strip()},
        )
