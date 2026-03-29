import json
from edge_audit import EdgeAuditEngine

if __name__ == "__main__":
    report = EdgeAuditEngine().compute_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
