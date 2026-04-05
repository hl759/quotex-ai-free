
from flask import Blueprint, current_app, jsonify


binary_bp = Blueprint("binary", __name__, url_prefix="/api/v1/binary")


def runtime():
    return current_app.config["RUNTIME"]


@binary_bp.get("/analyze")
def analyze():
    result = runtime().analyze_binary()
    return jsonify({"ok": True, "data": result})
