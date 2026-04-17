from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from alpha_hive.storage.state_store import get_state_store

COLLECTION = "journal_trades_v2"
LEGACY_COLLECTION = "journal_trades"


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

    def add_trade(self, payload: Dict[str, Any]) -> None:
        uid = str(payload.get("uid") or "")
        if not uid:
            uid = f"{payload.get('asset','NA')}-{payload.get('direction', payload.get('signal','NA'))}-{payload.get('analysis_time','--:--')}"
        enriched = {**payload, "uid": uid}
        self.store.upsert_collection_item(COLLECTION, uid, enriched)
        self.store.upsert_collection_item(LEGACY_COLLECTION, uid, enriched)

    def rows(self, limit: int = 4000) -> List[Dict[str, Any]]:
        current = self.store.list_collection(COLLECTION, limit=limit)
        legacy = self.store.list_collection(LEGACY_COLLECTION, limit=limit)

        merged: Dict[str, Dict[str, Any]] = {}

        for row in legacy:
            uid = str(row.get("uid") or f"{row.get('asset','NA')}-{row.get('direction', row.get('signal','NA'))}-{row.get('analysis_time','--:--')}")
            merged[uid] = {**row, "uid": uid}

        for row in current:
            uid = str(row.get("uid") or f"{row.get('asset','NA')}-{row.get('direction', row.get('signal','NA'))}-{row.get('analysis_time','--:--')}")
            merged[uid] = {**merged.get(uid, {}), **row, "uid": uid}

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
