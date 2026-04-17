from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from alpha_hive.services.snapshot_service import SnapshotService

bp = Blueprint("snapshot", __name__)
snapshot_service = SnapshotService()


@bp.get("/")
def home():
    scan_service = current_app.config["SCAN_SERVICE"]
    scan_service.ensure_started()
    return current_app.send_static_file("index.html")


@bp.get("/snapshot")
def snapshot():
    scan_service = current_app.config["SCAN_SERVICE"]
    scan_service.ensure_started()

    try:
        scan_service.auto_refresh_if_needed("snapshot_auto")
    except Exception:
        pass

    return jsonify(snapshot_service.build(scan_service.snapshot()))
