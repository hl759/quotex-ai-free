
import os
from pathlib import Path

from flask import Flask, jsonify

from api.routes.analytics import analytics_bp
from api.routes.binary import binary_bp
from api.routes.futures import futures_bp
from api.routes.system import system_bp
from core.runtime import TradingPlatformRuntime


runtime = TradingPlatformRuntime()


def create_app():
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config["RUNTIME"] = runtime

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = os.getenv("ALLOWED_ORIGINS", "*")
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    @app.errorhandler(Exception)
    def handle_error(exc):
        return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/")
    def root():
        return jsonify({
            "service": "alpha-hive-platform-api",
            "version": "2.0",
            "endpoints": [
                "/api/v1/system/health",
                "/api/v1/system/dashboard",
                "/api/v1/binary/analyze",
                "/api/v1/futures/analyze",
            ],
        })

    app.register_blueprint(system_bp)
    app.register_blueprint(binary_bp)
    app.register_blueprint(futures_bp)
    app.register_blueprint(analytics_bp)
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000") or 8000)
    app.run(host="0.0.0.0", port=port, debug=False)
