
from flask import Blueprint, current_app, jsonify, request

from core.security import json_body, to_bool


futures_bp = Blueprint("futures", __name__, url_prefix="/api/v1/futures")


def runtime():
    return current_app.config["RUNTIME"]


@futures_bp.post("/connect")
def connect():
    payload = json_body(request)
    status = runtime().connect_binance(
        api_key=payload.get("apiKey") or payload.get("api_key"),
        api_secret=payload.get("secretKey") or payload.get("api_secret"),
        testnet=to_bool(payload.get("testnet"), False),
    )
    return jsonify({"ok": True, "data": status})


@futures_bp.post("/disconnect")
def disconnect():
    return jsonify({"ok": True, "data": runtime().disconnect_binance()})


@futures_bp.get("/connection")
def connection():
    return jsonify({"ok": True, "data": runtime().connection_status()})


@futures_bp.get("/analyze")
def analyze():
    asset = request.args.get("asset")
    timeframe = request.args.get("timeframe", "1min")
    strategy_name = request.args.get("strategy", "institutional_confluence")
    result = runtime().analyze_futures(asset=asset, timeframe=timeframe, strategy_name=strategy_name, execution_mode="paper")
    return jsonify({"ok": True, "data": result})


@futures_bp.post("/execute")
def execute():
    payload = json_body(request)
    result = runtime().execute_futures(
        plan=payload.get("plan"),
        mode=payload.get("mode", "paper"),
        use_trailing_stop=to_bool(payload.get("useTrailingStop"), False),
        trailing_callback_rate=float(payload.get("trailingCallbackRate", 1.2) or 1.2),
    )
    return jsonify({"ok": bool(result.get("ok")), "data": result})


@futures_bp.get("/account")
def account():
    symbol = request.args.get("symbol")
    return jsonify({"ok": True, "data": runtime().futures_account_snapshot(symbol=symbol)})


@futures_bp.get("/positions")
def positions():
    symbol = request.args.get("symbol")
    snapshot = runtime().futures_account_snapshot(symbol=symbol)
    return jsonify({"ok": True, "data": snapshot.get("positions", [])})


@futures_bp.get("/orders/open")
def open_orders():
    symbol = request.args.get("symbol")
    snapshot = runtime().futures_account_snapshot(symbol=symbol)
    return jsonify({"ok": True, "data": snapshot.get("open_orders", [])})


@futures_bp.get("/orders/history")
def history_orders():
    symbol = request.args.get("symbol")
    snapshot = runtime().futures_account_snapshot(symbol=symbol)
    return jsonify({"ok": True, "data": snapshot.get("order_history", [])})


@futures_bp.post("/bot/start")
def bot_start():
    payload = json_body(request)
    state = runtime().bot_service.start({
        "symbol": payload.get("symbol", "BTCUSDT"),
        "timeframe": payload.get("timeframe", "1min"),
        "strategy": payload.get("strategy", "institutional_confluence"),
        "execution_mode": payload.get("executionMode", "paper"),
        "max_trades_per_day": int(float(payload.get("maxTradesPerDay", 6) or 6)),
        "poll_seconds": int(float(payload.get("pollSeconds", 20) or 20)),
        "use_trailing_stop": to_bool(payload.get("useTrailingStop"), False),
        "trailing_callback_rate": float(payload.get("trailingCallbackRate", 1.2) or 1.2),
    })
    return jsonify({"ok": True, "data": state})


@futures_bp.post("/bot/stop")
def bot_stop():
    return jsonify({"ok": True, "data": runtime().bot_service.stop()})


@futures_bp.get("/bot/status")
def bot_status():
    return jsonify({"ok": True, "data": runtime().bot_service.status()})


@futures_bp.post("/close-report")
def close_report():
    payload = json_body(request)
    result = runtime().close_futures_trade(payload)
    return jsonify({"ok": True, "data": result})
