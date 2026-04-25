from __future__ import annotations
from flask import Blueprint, jsonify, current_app
from alpha_hive.services.snapshot_service import SnapshotService

bp = Blueprint("snapshot", __name__)

def _svc():
    return current_app.config["SCAN_SERVICE"]

@bp.get("/snapshot")
def snapshot():
    scan_service = _svc()
    return jsonify(SnapshotService.build(scan_service.snapshot()))

@bp.get("/health")
def health():
    svc = _svc()
    return jsonify({"alive": True, "service": "alpha-hive", "status": "ok",
                    "uptime_seconds": round(svc.runtime.uptime, 2)})
