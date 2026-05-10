from __future__ import annotations

import os
import time
from pathlib import Path

from flask import Flask

from alpha_hive.app.routes.health import bp as health_bp
from alpha_hive.app.routes.vision import bp as vision_bp

_CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]


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

    app.config["START_TIME"] = time.time()

    app.register_blueprint(health_bp)
    app.register_blueprint(vision_bp)

    return app
