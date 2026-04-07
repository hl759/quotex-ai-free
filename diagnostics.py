from __future__ import annotations

from flask import Blueprint, jsonify

from alpha_hive.services.diagnostics_service import DiagnosticsService
from alpha_hive.services.learning_service import LearningService

bp = Blueprint("diagnostics", __name__)
diag = DiagnosticsService()
learning = LearningService()

@bp.get("/edge-report")
def edge_report():
    return jsonify(diag.edge_report())

@bp.get("/specialists")
def specialists():
    return jsonify(diag.specialists_report())

@bp.get("/memory-integrity")
def memory_integrity():
    return jsonify(diag.memory_integrity())

@bp.get("/storage-health")
def storage_health():
    return jsonify(diag.storage_health())

@bp.get("/learning-snapshot")
def learning_snapshot():
    return jsonify(learning.snapshot())
