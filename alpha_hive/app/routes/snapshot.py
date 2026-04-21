from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from alpha_hive.services.snapshot_service import SnapshotService

bp = Blueprint("snapshot", __name__)
snapshot_service = SnapshotService()


def _bootstrap_snapshot(scan_service) -> dict:
    """
    RENDER FREE: NÃO dispara scans automáticos a cada GET /snapshot.
    Apenas o background scanner inicia scans.
    Exceção: bootstrap (scan_count == 0) para ter dados na primeira abertura.
    """
    scan_service.ensure_started()

    meta = scan_service.runtime.setdefault("meta", {})
    meta["last_snapshot_refresh_error"] = ""
    meta["last_snapshot_refresh_result"] = {}

    try:
        current_state = scan_service.snapshot()
        current_meta = dict(current_state.get("meta", {}) or {})

        scan_count = int(current_meta.get("scan_count", 0) or 0)
        scan_in_progress = bool(current_meta.get("scan_in_progress", False))

        # Bootstrap: só roda scan se passive watcher já tem dados prontos
        # Evita timeout no cold start do Render Free
        passive_ready = False
        watcher = getattr(scan_service, "passive_watcher", None)
        if watcher:
            ctxs = watcher.get_all_contexts()
            passive_ready = sum(1 for c in ctxs.values() if c.is_initialized) >= 3

        if not scan_in_progress and scan_count <= 0 and passive_ready:
            refresh_result = scan_service.run_once("snapshot_bootstrap")
            if isinstance(refresh_result, dict):
                meta["last_snapshot_refresh_result"] = refresh_result
                if "evaluated" in refresh_result:
                    meta["pending_evaluated_last_scan"] = int(
                        refresh_result.get("evaluated", 0) or 0
                    )

        # REMOVIDO: pending_expired check e auto_refresh_if_needed
        # Esses dois chamavam run_once() em praticamente toda requisição GET.

    except Exception as exc:
        meta["last_snapshot_refresh_error"] = repr(exc)

    return snapshot_service.build(scan_service.snapshot())


@bp.get("/")
def home():
    scan_service = current_app.config["SCAN_SERVICE"]
    scan_service.ensure_started()
    return current_app.send_static_file("index.html")


@bp.get("/snapshot")
def snapshot():
    scan_service = current_app.config["SCAN_SERVICE"]
    return jsonify(_bootstrap_snapshot(scan_service))
