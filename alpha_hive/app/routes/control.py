from __future__ import annotations

import time
from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("control", __name__)

_last_trigger_ts: float = 0.0


@bp.route("/atualizar", methods=["GET", "POST"])
@bp.route("/run-scan", methods=["GET", "POST"])
def atualizar():
    """Active Decision Mode trigger — equivalente ao 'atualizar agora'."""
    global _last_trigger_ts

    settings = current_app.config["SETTINGS"]

    if not settings.scan_route_enabled:
        return jsonify({"ok": False, "error": "scan_route_disabled"}), 403

    if settings.scan_trigger_token:
        provided = (
            request.args.get("token")
            or request.headers.get("X-Scan-Token")
            or ""
        )
        if provided != settings.scan_trigger_token:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    now = time.time()
    elapsed = now - _last_trigger_ts
    min_interval = max(30, int(
        getattr(settings, "request_scan_min_interval_seconds", 120) or 120
    ))

    if elapsed < min_interval and _last_trigger_ts > 0:
        return jsonify({
            "ok": False,
            "skipped": True,
            "reason": "cooldown",
            "retry_after_seconds": int(min_interval - elapsed),
        })

    _last_trigger_ts = now
    service = current_app.config["SCAN_SERVICE"]
    service.ensure_started()
    result = service.run_once("atualizar_agora")
    return jsonify(result)


@bp.get("/passive-status")
def passive_status():
    """Diagnóstico do Passive Intelligence Mode."""
    service = current_app.config["SCAN_SERVICE"]
    watcher = getattr(service, "passive_watcher", None)
    if not watcher:
        return jsonify({"error": "passive_watcher_not_available"}), 503
    return jsonify(watcher.diagnostics())
