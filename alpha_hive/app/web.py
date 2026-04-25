from __future__ import annotations

import os
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
from alpha_hive.services.m1_m5_operability_patch import install_m1_m5_operability_patch

_CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
_SCAN_BUTTON_SCRIPT_TAG = '<script src="/js/scan_button.js?v=1"></script>'


def create_app() -> Flask:
    static_folder = str(Path(__file__).resolve().parent / "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="")

    if _CORS_ORIGINS:
        try:
            from flask_cors import CORS
            CORS(app, origins=_CORS_ORIGINS, supports_credentials=False)
        except ImportError:
            @app.after_request
            def add_cors(response):
                from flask import request as _req
                req_origin = _req.headers.get("Origin", "")
                if req_origin in _CORS_ORIGINS:
                    response.headers["Access-Control-Allow-Origin"] = req_origin
                    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                return response

    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass

    app.config["SETTINGS"] = SETTINGS
    install_m1_m5_operability_patch()
    scan_service = ScanService()
    app.config["SCAN_SERVICE"] = scan_service
    # Scan apenas via botão — loop autônomo permanentemente desligado.

    app.config["START_TIME"] = time.time()

    @app.after_request
    def optimize_response(response):
        path = getattr(response, "_request_path", "")
        if path and (path.endswith(".css") or path.endswith(".js")):
            response.cache_control.max_age = 3600
            response.cache_control.public = True

        content_type = (response.content_type or "").lower()
        if "text/html" in content_type and not response.is_streamed:
            try:
                body = response.get_data(as_text=True)
                if "scanStatusPill" in body and "scan_button.js" not in body:
                    body = body.replace("</body>", _SCAN_BUTTON_SCRIPT_TAG + "\n</body>")
                    response.set_data(body)
            except Exception:
                pass
        return response

    app.register_blueprint(health_bp)
    app.register_blueprint(snapshot_bp)
    app.register_blueprint(capital_bp)
    app.register_blueprint(control_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(vision_bp)

    return app
