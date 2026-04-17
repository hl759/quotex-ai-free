from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from alpha_hive.storage.state_store import get_state_store

COLLECTION = "journal_trades_v2"
LEGACY_COLLECTION = "journal_trades"

AUDIT_COLLECTION = "edge_trade_ledger_v2"
AUDIT_LEGACY_COLLECTION = "trade_ledger"


class JournalManager:
    def __init__(self):
        self.store = get_state_store()

    def _to_ts(self, value: Any) -> Optional[float]:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            val = float(value)
            return val if val > 0 else None

        text = str(value).strip()
        if not text:
            return None

        try:
            return float(text)
        except Exception:
            pass

        for candidate in (
            text.replace("Z", "+00:00"),
            text.replace(" UTC", "+00:00"),
            text,
        ):
            try:
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).timestamp()
            except Exception:
                continue

        return None

    def _row_sort_ts(self, row: Dict[str, Any]) -> float:
        for key in (
            "evaluated_at_ts",
            "signal_expiration_ts",
            "expires_at_ts",
            "exit_candle_ts",
            "signal_entry_ts",
            "entry_ts",
            "entry_candle_ts",
            "signal_analysis_ts",
            "analysis_ts",
            "created_at_ts",
        ):
            val = self._to_ts(row.get(key))
            if val is not None:
                return val
        return 0.0

    def _canonical_uid(self, row: Dict[str, Any]) -> str:
        return str(
            row.get("uid")
            or f"{row.get('asset','NA')}-{row.get('direction', row.get('signal','NA'))}-{row.get('analysis_time','--:--')}"
        )

    def _merge_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            uid = self._canonical_uid(row)
            merged[uid] = {**merged.get(uid, {}), **row, "uid": uid}
        return merged

    def add_trade(self, payload: Dict[str, Any]) -> None:
        uid = self._canonical_uid(payload)
        enriched = {**payload, "uid": uid}
        self.store.upsert_collection_item(COLLECTION, uid, enriched)
        self.store.upsert_collection_item(LEGACY_COLLECTION, uid, enriched)

    def _load_collection_rows(self, collection_name: str, limit: int) -> List[Dict[str, Any]]:
        return list(self.store.list_collection(collection_name, limit=limit) or [])

    def sync_from_audit(self, limit: int = 12000) -> int:
        journal_current = self._load_collection_rows(COLLECTION, limit)
        journal_legacy = self._load_collection_rows(LEGACY_COLLECTION, limit)

        audit_current = self._load_collection_rows(AUDIT_COLLECTION, limit)
        audit_legacy = self._load_collection_rows(AUDIT_LEGACY_COLLECTION, limit)

        journal_map = self._merge_rows(journal_current + journal_legacy)
        audit_map = self._merge_rows(audit_current + audit_legacy)

        missing = 0
        for uid, row in audit_map.items():
            if uid in journal_map:
                continue
            enriched = {**row, "uid": uid}
            self.store.upsert_collection_item(COLLECTION, uid, enriched)
            self.store.upsert_collection_item(LEGACY_COLLECTION, uid, enriched)
            missing += 1

        return missing

    def rows(self, limit: int = 12000) -> List[Dict[str, Any]]:
        # garante alinhamento com o audit antes de montar o histórico
        self.sync_from_audit(limit=limit)

        current = self._load_collection_rows(COLLECTION, limit)
        legacy = self._load_collection_rows(LEGACY_COLLECTION, limit)

        merged = self._merge_rows(legacy + current)
        rows = list(merged.values())
        rows.sort(key=self._row_sort_ts, reverse=True)
        return rows[:limit]

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
