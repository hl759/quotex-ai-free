from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("control", __name__)


@bp.route("/atualizar", methods=["GET", "POST"])
@bp.route("/run-scan", methods=["GET", "POST"])
def atualizar():
    """Endpoint de diagnóstico — o scan já ocorre automaticamente a cada ciclo."""
    settings = current_app.config["SETTINGS"]
    if settings.scan_trigger_token:
        provided = (
            request.args.get("token")
            or request.headers.get("X-Scan-Token")
            or ""
        )
        if provided != settings.scan_trigger_token:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    service = current_app.config["SCAN_SERVICE"]
    result = service.run_once("manual")
    return jsonify(result)


@bp.get("/scan-status")
def scan_status():
    """Status do loop autônomo de scan."""
    service = current_app.config["SCAN_SERVICE"]
    meta = service._meta()
    return jsonify({
        "loop_active": service._started,
        "scan_interval_seconds": current_app.config["SETTINGS"].scan_interval_seconds,
        "last_scan": meta.get("last_scan", "--"),
        "last_scan_age_seconds": service._scan_age_seconds(),
        "scan_count": meta.get("scan_count", 0),
        "scan_in_progress": meta.get("scan_in_progress", False),
    })
