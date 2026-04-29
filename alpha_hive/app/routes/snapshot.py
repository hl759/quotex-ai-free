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
    # Passa o relatório já cacheado (30s TTL) — evita criar nova instância
    # pesada de EdgeAuditEngine a cada ping do UptimeRobot/BetterStack.
    audit_report = scan_service.audit.compute_report()
    return jsonify(snapshot_service.build(scan_service.snapshot(), audit_report=audit_report))
