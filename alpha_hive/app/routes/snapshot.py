from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from alpha_hive.services.snapshot_service import SnapshotService

bp = Blueprint("snapshot", __name__)
snapshot_service = SnapshotService()


@bp.get("/")
def home():
    scan_service = current_app.config["SCAN_SERVICE"]
    # ON-DEMAND: se background scanner estiver ativo, garante que está rodando
    if current_app.config["SETTINGS"].run_background_scanner:
        scan_service.ensure_started()
    return current_app.send_static_file("index.html")


@bp.get("/snapshot")
def snapshot():
    """
    Leitura pura do estado em memória — NÃO dispara nenhum scan.
    ON-DEMAND MODE: o scan só ocorre via POST /atualizar (clique do usuário).
    Chama maybe_cleanup_idle() para liberar histórico excessivo após inatividade.
    """
    scan_service = current_app.config["SCAN_SERVICE"]
    scan_service.maybe_cleanup_idle()
    return jsonify(snapshot_service.build(scan_service.snapshot()))
