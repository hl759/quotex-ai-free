from __future__ import annotations

import time
from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("control", __name__)

_last_trigger_ts: float = 0.0


@bp.route("/atualizar", methods=["GET", "POST"])
@bp.route("/run-scan", methods=["GET", "POST"])
def atualizar():
    """
    ON-DEMAND scan trigger — único ponto de ativação da inteligência.
    Chamado exclusivamente pelo botão "Atualizar agora" na UI.
    Não há polling automático nem background loops no modo padrão.
    """
    global _last_trigger_ts

    settings = current_app.config["SETTINGS"]

    if not settings.scan_route_enabled:
        return jsonify({"ok": False, "error": "scan_route_disabled"}), 403

    if settings.scan_trigger_token:
        provided = (
            request.args.get("token")
            or request.headers.get("X-Scan-Token")
            or ""
        )
        if provided != settings.scan_trigger_token:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    now = time.time()
    elapsed = now - _last_trigger_ts
    # Cooldown reduzido para 30s no modo on-demand (era 120s para background mode)
    min_interval = max(30, int(
        getattr(settings, "request_scan_min_interval_seconds", 30) or 30
    ))

    if elapsed < min_interval and _last_trigger_ts > 0:
        return jsonify({
            "ok": False,
            "skipped": True,
            "reason": "cooldown",
            "retry_after_seconds": int(min_interval - elapsed),
        })

    _last_trigger_ts = now
    service = current_app.config["SCAN_SERVICE"]
    result = service.run_once("atualizar_agora")
    # Se o scan falhou, resetar cooldown para permitir nova tentativa imediata
    if isinstance(result, dict) and not result.get("ok", True):
        _last_trigger_ts = 0.0
    return jsonify(result)


@bp.get("/passive-status")
def passive_status():
    """Diagnóstico do modo de coleta de dados."""
    service = current_app.config["SCAN_SERVICE"]
    settings = current_app.config["SETTINGS"]
    watcher = getattr(service, "passive_watcher", None)
    mode = "background" if settings.run_background_scanner else "on_demand"
    if not watcher:
        return jsonify({"mode": mode, "error": "passive_watcher_not_available"}), 503
    return jsonify({"mode": mode, **watcher.diagnostics()})
