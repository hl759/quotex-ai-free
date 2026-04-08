from __future__ import annotations

from flask import Blueprint, jsonify, request

from alpha_hive.services.capital_service import CapitalService

bp = Blueprint("capital", __name__)
service = CapitalService()

@bp.get("/capital-state")
def capital_get():
    return jsonify(service.get())

@bp.post("/capital-state")
def capital_post():
    payload = request.get_json(silent=True) or {}
    return jsonify(service.save(payload))
