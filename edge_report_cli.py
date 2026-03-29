import json
from json_safe import safe_dumps
from edge_audit import EdgeAuditEngine
from edge_guard import EdgeGuardEngine

if __name__ == "__main__":
    report = EdgeAuditEngine().compute_report()
    guard = EdgeGuardEngine().evaluate(asset="GLOBAL", regime="global", strategy_name="global", analysis_time=None, proposed_decision="OBSERVAR", proposed_score=0.0, proposed_confidence=50)
    print(safe_dumps({"edge_report": report, "edge_guard": guard}, indent=2))
