
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from core.security import json_body


system_bp = Blueprint("system", __name__, url_prefix="/api/v1/system")


def runtime():
    return current_app.config["RUNTIME"]


@system_bp.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "alpha-hive-platform-api",
        "mode": runtime().get_mode(),
        "binance": runtime().connection_status(),
    })


@system_bp.route("/mode", methods=["GET", "POST"])
def mode():
    if request.method == "POST":
        payload = json_body(request)
        active = runtime().set_mode(payload.get("mode", "BINARY_MODE"))
        return jsonify({"ok": True, "active_mode": active})
    return jsonify({"ok": True, "active_mode": runtime().get_mode()})


@system_bp.get("/dashboard")
def dashboard():
    return jsonify({"ok": True, "data": runtime().dashboard_snapshot()})


@system_bp.get("/logs")
def logs():
    log_dir = os.getenv("ALPHA_HIVE_LOG_DIR", os.path.join(os.getcwd(), "logs"))
    path = Path(log_dir) / "platform.log"
    if not path.exists():
        return jsonify({"ok": True, "lines": []})
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]
    return jsonify({"ok": True, "lines": lines})
