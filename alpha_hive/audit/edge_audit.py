from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from alpha_hive.storage.state_store import get_state_store

COLLECTION = "edge_trade_ledger_v2"
LEGACY_COLLECTION = "trade_ledger"


class EdgeAuditEngine:
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

    def record_trade(self, payload: Dict[str, Any]) -> None:
        uid = str(payload.get("uid") or "")
        if not uid:
            uid = f"{payload.get('asset','NA')}-{payload.get('direction', payload.get('signal','NA'))}-{payload.get('analysis_time','--:--')}"
        enriched = {**payload, "uid": uid}
        self.store.upsert_collection_item(COLLECTION, uid, enriched)
        self.store.upsert_collection_item(LEGACY_COLLECTION, uid, enriched)

    def load_ledger(self, limit: int = 10000) -> List[Dict[str, Any]]:
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

    def _summary(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid = [row for row in rows if str(row.get("result", "")).upper() in ("WIN", "LOSS")]
        total = len(valid)
        if not total:
            return {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "winrate": 0.0,
                "expectancy_r": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
            }
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

    def _extract_hour(self, row: Dict[str, Any]) -> str:
        hour_bucket = str(row.get("hour_bucket", "") or "").strip()
        if hour_bucket:
            if ":" in hour_bucket:
                return hour_bucket.split(":")[0].zfill(2)
            return hour_bucket[:2].zfill(2)

        analysis_time = str(row.get("analysis_time", "") or "").strip()
        if analysis_time and ":" in analysis_time:
            return analysis_time.split(":")[0].zfill(2)

        entry_time = str(row.get("entry_time", "") or "").strip()
        if entry_time and ":" in entry_time:
            return entry_time.split(":")[0].zfill(2)

        expiration = str(row.get("expiration", "") or "").strip()
        if expiration and ":" in expiration:
            return expiration.split(":")[0].zfill(2)

        return "unknown"

    def _group_hours(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            hour = self._extract_hour(row)
            if hour == "unknown":
                continue
            groups.setdefault(hour, []).append(row)

        out = []
        for hour, bucket in groups.items():
            stats = self._summary(bucket)
            stats["hour"] = hour
            out.append(stats)

        out.sort(
            key=lambda item: (
                item.get("expectancy_r", 0.0),
                item.get("winrate", 0.0),
                item.get("total", 0),
            ),
            reverse=True,
        )
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
            "by_hour": self._group_hours(rows)[:12],
        }
