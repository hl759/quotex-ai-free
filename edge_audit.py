from __future__ import annotations

import math
from typing import Any, Dict, List

from alpha_hive.storage.state_store import get_state_store

COLLECTION = "edge_trade_ledger_v2"

class EdgeAuditEngine:
    def __init__(self):
        self.store = get_state_store()

    def record_trade(self, payload: Dict[str, Any]) -> None:
        uid = str(payload.get("uid"))
        self.store.upsert_collection_item(COLLECTION, uid, payload)

    def load_ledger(self, limit: int = 10000) -> List[Dict[str, Any]]:
        return self.store.list_collection(COLLECTION, limit=limit)

    def _summary(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid = [row for row in rows if str(row.get("result", "")).upper() in ("WIN", "LOSS")]
        total = len(valid)
        if not total:
            return {"total": 0, "wins": 0, "losses": 0, "winrate": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0}
        wins = sum(1 for row in valid if str(row.get("result", "")).upper() == "WIN")
        losses = total - wins
        rs = [float(row.get("gross_r", 0.0) or 0.0) for row in valid]
        pnls = [float(row.get("gross_pnl", 0.0) or 0.0) for row in valid]
        gross_profit = sum(x for x in pnls if x > 0)
        gross_loss = abs(sum(x for x in pnls if x < 0))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "winrate": round((wins / total) * 100, 2),
            "expectancy_r": round(sum(rs) / len(rs), 4),
            "profit_factor": round(pf, 3),
            "total_pnl": round(sum(pnls), 2),
        }

    def _group(self, rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(str(row.get(key, "unknown")), []).append(row)
        out = []
        for name, bucket in groups.items():
            stats = self._summary(bucket)
            stats[key] = name
            out.append(stats)
        out.sort(key=lambda item: (item.get("expectancy_r", 0.0), item.get("winrate", 0.0), item.get("total", 0)), reverse=True)
        return out

    def compute_report(self) -> Dict[str, Any]:
        rows = self.load_ledger()
        return {
            "summary": self._summary(rows),
            "recent_20": self._summary(rows[:20]),
            "recent_50": self._summary(rows[:50]),
            "by_asset": self._group(rows, "asset")[:10],
            "by_provider": self._group(rows, "provider")[:10],
            "by_specialist": self._group(rows, "dominant_specialist")[:10],
            "by_state": self._group(rows, "state")[:10],
        }
