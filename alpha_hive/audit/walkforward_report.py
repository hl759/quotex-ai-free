from __future__ import annotations

from typing import Dict

from alpha_hive.audit.edge_audit import EdgeAuditEngine

class WalkForwardReport:
    def __init__(self):
        self.audit = EdgeAuditEngine()

    def generate(self) -> Dict[str, object]:
        report = self.audit.compute_report()
        return {
            "summary": report.get("summary", {}),
            "recent_20": report.get("recent_20", {}),
            "recent_50": report.get("recent_50", {}),
            "note": "Base inicial para robustez e acompanhamento walk-forward.",
        }
