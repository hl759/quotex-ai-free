from __future__ import annotations

from typing import Any, Dict, List

from alpha_hive.storage.state_store import get_state_store

COLLECTION = "journal_trades_v2"
LEGACY_COLLECTION = "journal_trades"

class JournalManager:
    def __init__(self):
        self.store = get_state_store()

    def add_trade(self, payload: Dict[str, Any]) -> None:
        uid = str(payload.get("uid") or "")
        if not uid:
            uid = f"{payload.get('asset','NA')}-{payload.get('direction', payload.get('signal','NA'))}-{payload.get('analysis_time','--:--')}"
        self.store.upsert_collection_item(COLLECTION, uid, payload)
        self.store.upsert_collection_item(LEGACY_COLLECTION, uid, payload)

    def rows(self, limit: int = 4000) -> List[Dict[str, Any]]:
        rows = self.store.list_collection(COLLECTION, limit=limit)
        if rows:
            return rows
        return self.store.list_collection(LEGACY_COLLECTION, limit=limit)

    def stats(self) -> Dict[str, Any]:
        rows = [row for row in self.rows() if str(row.get("result", "")).upper() in ("WIN", "LOSS")]
        total = len(rows)
        wins = sum(1 for row in rows if str(row.get("result", "")).upper() == "WIN")
        pnl = sum(float(row.get("gross_pnl", 0.0) or 0.0) for row in rows)
        winrate = round((wins / total) * 100, 2) if total else 0.0
        return {
            "total": total,
            "wins": wins,
            "loss": total - wins,
            "winrate": winrate,
            "total_pnl": round(pnl, 2),
        }
