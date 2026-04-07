from __future__ import annotations

import time
from flask import Blueprint, current_app, jsonify

bp = Blueprint("health", __name__)

@bp.get("/health")
def health():
    started = current_app.config["START_TIME"]
    return jsonify({
        "status": "ok",
        "service": "alpha-hive",
        "alive": True,
        "uptime_seconds": round(time.time() - started, 2),
    })
