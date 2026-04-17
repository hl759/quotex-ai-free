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

    meta = scan_service.runtime.setdefault("meta", {})
    meta["last_snapshot_refresh_error"] = ""
    meta["last_snapshot_refresh_result"] = {}

    try:
        current_state = scan_service.snapshot()
        current_meta = dict(current_state.get("meta", {}) or {})

        scan_count = int(current_meta.get("scan_count", 0) or 0)
        pending_expired = int(current_meta.get("pending_expired", 0) or 0)
        scan_in_progress = bool(current_meta.get("scan_in_progress", False))

        refresh_result = None

        if not scan_in_progress:
            if scan_count <= 0:
                refresh_result = scan_service.run_once("snapshot_bootstrap")
            elif pending_expired > 0:
                refresh_result = scan_service.run_once("snapshot_liquidation")
            else:
                refresh_result = scan_service.auto_refresh_if_needed("snapshot_auto")

        if isinstance(refresh_result, dict):
            meta["last_snapshot_refresh_result"] = refresh_result
            if "evaluated" in refresh_result:
                meta["pending_evaluated_last_scan"] = int(refresh_result.get("evaluated", 0) or 0)

    except Exception as exc:
        meta["last_snapshot_refresh_error"] = repr(exc)

    return jsonify(snapshot_service.build(scan_service.snapshot()))
