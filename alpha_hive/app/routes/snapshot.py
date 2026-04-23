from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from alpha_hive.services.snapshot_service import SnapshotService

bp = Blueprint("snapshot", __name__)
snapshot_service = SnapshotService()


@bp.get("/")
def home():
    return current_app.send_static_file("index.html")


@bp.get("/snapshot")
def snapshot():
    scan_service = current_app.config["SCAN_SERVICE"]
    scan_service.maybe_cleanup_idle()
    return jsonify(snapshot_service.build(scan_service.snapshot()))
