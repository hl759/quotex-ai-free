
import math
import time
from copy import deepcopy

from core.security import sanitize_error


class FuturesExecutionService:
    def __init__(self, client, self_optimizer=None, logger=None):
        self.client = client
        self.self_optimizer = self_optimizer
        self.logger = logger

    def _log(self, message, level="info"):
        if not self.logger:
            return
        getattr(self.logger, level, self.logger.info)(message)

    def _safe_float(self, value, default=0.0):
        try:
            if value is None or value == "":
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def validate_plan(self, plan):
        if not isinstance(plan, dict):
            return False, "invalid_plan"
        if str(plan.get("status", "")).upper() != "READY":
            return False, "plan_not_ready"
        if not str(plan.get("asset", "")).strip():
            return False, "missing_symbol"
        if not str(plan.get("direction", "")).upper() in ("LONG", "SHORT"):
            return False, "missing_direction"
        qty = self._safe_float(plan.get("quantity"), 0.0)
        if qty <= 0:
            return False, "invalid_quantity"
        leverage = int(self._safe_float(plan.get("leverage"), 0))
        if leverage <= 0:
            return False, "invalid_leverage"
        return True, "ok"

    def build_order_bundle(self, plan, use_trailing_stop=False, trailing_callback_rate=1.2):
        direction = str(plan.get("direction", "LONG")).upper()
        side = "BUY" if direction == "LONG" else "SELL"
        exit_side = "SELL" if side == "BUY" else "BUY"
        quantity = round(self._safe_float(plan.get("quantity"), 0.0), 6)
        symbol = str(plan.get("asset"))
        stop_price = self._safe_float(plan.get("stop_loss"), 0.0)
        take_profits = list(plan.get("take_profits", []))

        orders = [
            {
                "kind": "entry",
                "payload": {
                    "symbol": symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": quantity,
                    "newOrderRespType": "RESULT",
                },
            },
            {
                "kind": "protective_stop",
                "payload": {
                    "symbol": symbol,
                    "side": exit_side,
                    "type": "STOP_MARKET",
                    "stopPrice": stop_price,
                    "quantity": quantity,
                    "reduceOnly": "true",
                    "workingType": "MARK_PRICE",
                },
            },
        ]

        if use_trailing_stop:
            orders.append({
                "kind": "trailing_stop",
                "payload": {
                    "symbol": symbol,
                    "side": exit_side,
                    "type": "TRAILING_STOP_MARKET",
                    "quantity": quantity,
                    "callbackRate": round(max(0.1, min(10.0, float(trailing_callback_rate))), 2),
                    "reduceOnly": "true",
                    "workingType": "MARK_PRICE",
                },
            })
        else:
            for tp in take_profits:
                tp_qty = quantity * (self._safe_float(tp.get("size_pct"), 0.0) / 100.0)
                tp_qty = round(tp_qty, 6)
                if tp_qty <= 0:
                    continue
                orders.append({
                    "kind": str(tp.get("label") or "tp").lower(),
                    "payload": {
                        "symbol": symbol,
                        "side": exit_side,
                        "type": "TAKE_PROFIT_MARKET",
                        "stopPrice": self._safe_float(tp.get("price"), 0.0),
                        "quantity": tp_qty,
                        "reduceOnly": "true",
                        "workingType": "MARK_PRICE",
                    },
                })
        return orders

    def execute_plan(self, plan, mode="paper", use_trailing_stop=False, trailing_callback_rate=1.2):
        valid, message = self.validate_plan(plan)
        if not valid:
            return {
                "ok": False,
                "mode": mode,
                "message": message,
                "plan": deepcopy(plan),
            }

        bundle = self.build_order_bundle(plan, use_trailing_stop=use_trailing_stop, trailing_callback_rate=trailing_callback_rate)
        if str(mode).lower() != "live":
            self._log(f"paper execution prepared for {plan.get('asset')} {plan.get('direction')}")
            return {
                "ok": True,
                "executed": False,
                "mode": "paper",
                "message": "paper_bundle_prepared",
                "orders": bundle,
                "plan": deepcopy(plan),
            }

        responses = []
        try:
            self.client.change_leverage(symbol=plan["asset"], leverage=int(plan["leverage"]))
            for order in bundle:
                responses.append({
                    "kind": order["kind"],
                    "response": self.client.new_order(**order["payload"]),
                })
            self._log(f"live futures execution sent for {plan.get('asset')} {plan.get('direction')}")
            return {
                "ok": True,
                "executed": True,
                "mode": "live",
                "message": "orders_submitted",
                "exchange": "binance_futures",
                "responses": responses,
                "plan": deepcopy(plan),
            }
        except Exception as exc:
            self._log(f"live futures execution failed: {sanitize_error(exc)}", level="error")
            return {
                "ok": False,
                "executed": False,
                "mode": "live",
                "message": sanitize_error(exc),
                "responses": responses,
                "plan": deepcopy(plan),
            }

    def register_close_report(self, report):
        if not self.self_optimizer:
            return report
        return self.self_optimizer.register_futures_close(report)
