from __future__ import annotations

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.services.capital_service import CapitalService

class SnapshotService:
    def __init__(self):
        self.audit = EdgeAuditEngine()
        self.journal = JournalManager()
        self.capital = CapitalService()

    def build(self, runtime: dict):
        return {
            "signals": runtime.get("signals", []),
            "history": runtime.get("history", []),
            "current_decision": runtime.get("current_decision", {}),
            "meta": runtime.get("meta", {}),
            "learning_stats": self.journal.stats(),
            "best_assets": self.audit.compute_report().get("by_asset", []),
            "best_hours": [],
            "capital_state": self.capital.get(),
            "specialist_leaders": self.audit.compute_report().get("by_specialist", []),
        }
