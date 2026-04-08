from __future__ import annotations

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine
from alpha_hive.storage.state_store import get_state_store

class DiagnosticsService:
    def __init__(self):
        self.audit = EdgeAuditEngine()
        self.specialists = SpecialistReputationEngine()
        self.store = get_state_store()

    def edge_report(self):
        return self.audit.compute_report()

    def specialists_report(self):
        return {"leaders": self.specialists.snapshot(limit=25)}

    def storage_health(self):
        return self.store.health()

    def memory_integrity(self):
        return {
            "durable_ready": self.store.backend_name in ("sqlite", "postgres"),
            "backend": self.store.backend_name,
            "target": self.store.backend_target,
            "fallback_reason": self.store.fallback_reason,
            "last_error": self.store.last_error,
        }
