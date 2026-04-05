
from flask import Blueprint, current_app, jsonify


analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/v1/analytics")


def runtime():
    return current_app.config["RUNTIME"]


@analytics_bp.get("/performance")
def performance():
    return jsonify({"ok": True, "data": runtime().analytics_snapshot()})
