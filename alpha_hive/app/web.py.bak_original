from __future__ import annotations

import time
from pathlib import Path

from flask import Flask

from alpha_hive.app.routes.capital import bp as capital_bp
from alpha_hive.app.routes.control import bp as control_bp
from alpha_hive.app.routes.diagnostics import bp as diagnostics_bp
from alpha_hive.app.routes.health import bp as health_bp
from alpha_hive.app.routes.snapshot import bp as snapshot_bp
from alpha_hive.config import SETTINGS
from alpha_hive.services.scan_service import ScanService

def create_app() -> Flask:
    static_folder = str(Path(__file__).resolve().parent / "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="")
    app.config["SETTINGS"] = SETTINGS
    app.config["SCAN_SERVICE"] = ScanService()
    app.config["START_TIME"] = time.time()
    app.register_blueprint(health_bp)
    app.register_blueprint(snapshot_bp)
    app.register_blueprint(capital_bp)
    app.register_blueprint(control_bp)
    app.register_blueprint(diagnostics_bp)
    return app
