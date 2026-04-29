from __future__ import annotations

import time

import requests
from flask import Blueprint, current_app, jsonify

from alpha_hive.services.diagnostics_service import DiagnosticsService
from alpha_hive.services.learning_service import LearningService

bp = Blueprint("diagnostics", __name__)
diag = DiagnosticsService()
learning = LearningService()

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@bp.get("/probe")
def probe():
    """Testa conectividade com cada provedor de dados. Acesse /probe para diagnosticar."""
    results = {}
    headers = {"User-Agent": _BROWSER_UA, "Accept": "application/json,text/plain,*/*"}
    now = int(time.time())

    # Binance
    t = time.time()
    try:
        r = requests.get(
            "https://data-api.binance.vision/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1m", "limit": 5},
            headers=headers, timeout=6,
        )
        data = r.json()
        results["binance"] = {"ok": isinstance(data, list) and len(data) > 0, "candles": len(data) if isinstance(data, list) else 0, "ms": int((time.time()-t)*1000)}
    except Exception as e:
        results["binance"] = {"ok": False, "error": str(e)[:120], "ms": int((time.time()-t)*1000)}

    # Yahoo Finance crypto
    t = time.time()
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD",
            params={"interval": "1m", "period1": now - 3600, "period2": now},
            headers=headers, timeout=6,
        )
        data = r.json()
        ts = ((data.get("chart") or {}).get("result") or [{}])[0].get("timestamp") or []
        results["yahoo_crypto"] = {"ok": len(ts) > 0, "candles": len(ts), "http": r.status_code, "ms": int((time.time()-t)*1000)}
    except Exception as e:
        results["yahoo_crypto"] = {"ok": False, "error": str(e)[:120], "ms": int((time.time()-t)*1000)}

    # Yahoo Finance forex
    t = time.time()
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X",
            params={"interval": "1m", "period1": now - 3600, "period2": now},
            headers=headers, timeout=6,
        )
        data = r.json()
        ts = ((data.get("chart") or {}).get("result") or [{}])[0].get("timestamp") or []
        results["yahoo_forex"] = {"ok": len(ts) > 0, "candles": len(ts), "http": r.status_code, "ms": int((time.time()-t)*1000)}
    except Exception as e:
        results["yahoo_forex"] = {"ok": False, "error": str(e)[:120], "ms": int((time.time()-t)*1000)}

    # Last scan state
    scan_service = current_app.config.get("SCAN_SERVICE")
    meta = {}
    if scan_service:
        meta = dict(scan_service._meta())

    return jsonify({
        "providers": results,
        "all_ok": all(v.get("ok") for v in results.values()),
        "last_scan_error": meta.get("last_scan_error", ""),
        "scan_count": meta.get("scan_count", 0),
        "asset_count": meta.get("asset_count", 0),
        "last_scan": meta.get("last_scan", "--"),
    })


@bp.get("/edge-report")
def edge_report():
    return jsonify(diag.edge_report())

@bp.get("/specialists")
def specialists():
    return jsonify(diag.specialists_report())

@bp.get("/memory-integrity")
def memory_integrity():
    return jsonify(diag.memory_integrity())

@bp.get("/storage-health")
def storage_health():
    return jsonify(diag.storage_health())

@bp.get("/learning-snapshot")
def learning_snapshot():
    return jsonify(learning.snapshot())
