from __future__ import annotations

import time
from pathlib import Path

from flask import Flask

from alpha_hive.app.routes.capital import bp as capital_bp
from alpha_hive.app.routes.control import bp as control_bp
from alpha_hive.app.routes.diagnostics import bp as diagnostics_bp
from alpha_hive.app.routes.health import bp as health_bp
from alpha_hive.app.routes.snapshot import bp as snapshot_bp
from alpha_hive.app.routes.vision import bp as vision_bp
from alpha_hive.config import SETTINGS
from alpha_hive.services.scan_service import ScanService


def create_app() -> Flask:
    static_folder = str(Path(__file__).resolve().parent / "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="")

    # ── Compressão gzip (RENDER FREE: reduz JSON em ~65-75%) ─────────────────
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass  # flask-compress não instalado: continua sem compressão

    app.config["SETTINGS"] = SETTINGS
    scan_service = ScanService()
    app.config["SCAN_SERVICE"] = scan_service
    scan_service.ensure_started()  # inicia passive watcher no startup
    app.config["START_TIME"] = time.time()

    # ── Cache-Control para arquivos estáticos ─────────────────────────────────
    @app.after_request
    def add_cache_headers(response):
        path = getattr(response, "_request_path", "")
        if path and (path.endswith(".css") or path.endswith(".js")):
            response.cache_control.max_age = 3600
            response.cache_control.public = True
        return response

    app.register_blueprint(health_bp)
    app.register_blueprint(snapshot_bp)
    app.register_blueprint(capital_bp)
    app.register_blueprint(control_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(vision_bp)

    return app
