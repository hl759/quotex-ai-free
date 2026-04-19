from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("control", __name__)


@bp.route("/run-scan", methods=["GET", "POST"])
def run_scan():
    settings = current_app.config["SETTINGS"]
    if not settings.scan_route_enabled:
        return jsonify({"ok": False, "error": "scan_route_disabled"}), 403
    if settings.scan_trigger_token:
        provided = request.args.get("token") or request.headers.get("X-Scan-Token") or ""
        if provided != settings.scan_trigger_token:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
    service = current_app.config["SCAN_SERVICE"]
    service.ensure_started()
    result = service.run_once("manual")
    return jsonify(result)
