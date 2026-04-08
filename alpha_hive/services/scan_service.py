from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.audit.result_engine import ResultEngine
from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import FinalDecision, MarketSnapshot
from alpha_hive.intelligence.decision_engine import DecisionEngine
from alpha_hive.intelligence.signal_engine import SignalEngine
from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine
from alpha_hive.market.scanner import MarketScanner
from alpha_hive.services.capital_service import CapitalService
from alpha_hive.storage.state_store import get_state_store

PENDING_COLLECTION = "pending_signals_v2"


class ScanService:
    def __init__(self):
        self.scanner = MarketScanner()
        self.decision_engine = DecisionEngine()
        self.signal_engine = SignalEngine()
        self.result_engine = ResultEngine()
        self.capital_service = CapitalService()
        self.learning = LearningEngine()
        self.specialists = SpecialistReputationEngine()
        self.audit = EdgeAuditEngine()
        self.journal = JournalManager()
        self.store = get_state_store()
        self.runtime: Dict[str, object] = {
            "signals": [],
            "history": [],
            "current_decision": {},
            "meta": {
                "last_scan": "--",
                "scan_count": 0,
                "signal_count": 0,
                "asset_count": 0,
                "scan_in_progress": False,
                "last_scan_age_seconds": 0,
                "ui_auto_refresh_seconds": SETTINGS.ui_auto_refresh_seconds,
                "ui_stale_after_seconds": SETTINGS.ui_stale_after_seconds,
                "ui_force_scan_after_seconds": SETTINGS.ui_force_scan_after_seconds,
            },
        }
        self._lock = threading.Lock()
        self._started = False

    def _find_snapshot(self, snapshots: List[MarketSnapshot], asset: str) -> Optional[MarketSnapshot]:
        return next((snap for snap in snapshots if snap.asset == asset), None)

    def _build_pending_payload(self, decision: FinalDecision) -> Dict[str, Any]:
        base = now_brazil().replace(second=0, microsecond=0)
        entry_epoch = base.timestamp() + 60
        expiration_epoch = base.timestamp() + 120
        analysis_key = base.strftime("%Y%m%d%H%M")
        direction = str(decision.direction or "NA")
        uid = f"{decision.asset}-{direction}-{analysis_key}"
        dominant_specialist = decision.council.get("top_specialists", ["unknown"])[0] if decision.council else "unknown"
        return {
            "uid": uid,
            "status": "pending",
            "asset": decision.asset,
            "decision": decision.decision,
            "direction": decision.direction,
            "provider": decision.provider,
            "market_type": decision.market_type,
            "state": decision.state,
            "score": decision.score,
            "confidence": decision.confidence,
            "setup_quality": decision.setup_quality,
            "consensus_quality": decision.consensus_quality,
            "execution_permission": decision.execution_permission,
            "suggested_stake": decision.suggested_stake,
            "risk_pct": decision.risk_pct,
            "features": decision.features,
            "council": decision.council,
            "reasons": decision.reasons,
            "dominant_specialist": dominant_specialist,
            "analysis_time": base.strftime("%H:%M"),
            "entry_time": time.strftime("%H:%M", time.localtime(entry_epoch)),
            "expiration": time.strftime("%H:%M", time.localtime(expiration_epoch)),
            "created_at_ts": time.time(),
            "expires_at_ts": expiration_epoch,
        }

    def _schedule_pending(self, decision: Optional[FinalDecision]) -> None:
        if not decision or decision.direction not in ("CALL", "PUT"):
            return
        if decision.execution_permission == "BLOQUEADO":
            return
        payload = self._build_pending_payload(decision)
        self.store.upsert_collection_item(PENDING_COLLECTION, payload["uid"], payload)

    def _pending_rows(self) -> List[Dict[str, Any]]:
        rows = self.store.list_collection(PENDING_COLLECTION, limit=300)
        return [row for row in rows if str(row.get("status", "pending")) == "pending"]

    def _decision_from_pending(self, row: Dict[str, Any]) -> FinalDecision:
        return FinalDecision(
            asset=str(row.get("asset", "")),
            state=str(row.get("state", "OBSERVE")),
            decision=str(row.get("decision", "OBSERVAR")),
            direction=row.get("direction"),
            confidence=int(row.get("confidence", 50) or 50),
            score=float(row.get("score", 0.0) or 0.0),
            setup_quality=str(row.get("setup_quality", "monitorado")),
            consensus_quality=str(row.get("consensus_quality", "split")),
            execution_permission=str(row.get("execution_permission", "BLOQUEADO")),
            suggested_stake=float(row.get("suggested_stake", 0.0) or 0.0),
            risk_pct=float(row.get("risk_pct", 0.0) or 0.0),
            provider=str(row.get("provider", "unknown")),
            market_type=str(row.get("market_type", "unknown")),
            reasons=list(row.get("reasons", []) or []),
            specialist_votes=[],
            council=dict(row.get("council", {}) or {}),
            risk={},
            features=dict(row.get("features", {}) or {}),
        )

    def _register_outcome(self, row: Dict[str, Any], snapshot: MarketSnapshot) -> None:
        decision = self._decision_from_pending(row)
        outcome = self.result_engine.evaluate_expired_decision(decision, snapshot.candles_m1[-2:])
        if not outcome:
            return

        dominant_specialist = str(row.get("dominant_specialist", "unknown"))
        regime = str(decision.features.get("regime", "unknown"))
        provider_root = str(decision.provider or "unknown").split("-")[0]
        hour_bucket = now_brazil().strftime("%H:00")

        payload = {
            **outcome.to_dict(),
            "asset": decision.asset,
            "signal": decision.direction,
            "direction": decision.direction,
            "provider": decision.provider,
            "state": decision.state,
            "dominant_specialist": dominant_specialist,
            "analysis_time": row.get("analysis_time"),
            "entry_time": row.get("entry_time"),
            "expiration": row.get("expiration"),
            "setup_quality": decision.setup_quality,
            "regime": regime,
            "risk_pct": decision.risk_pct,
            "score": decision.score,
            "confidence": decision.confidence,
        }

        self.audit.record_trade(payload)
        self.journal.add_trade(payload)

        self.learning.register_outcome(
            decision.asset,
            str(decision.direction),
            regime,
            dominant_specialist,
            provider_root,
            decision.market_type,
            hour_bucket,
            decision.setup_quality,
            outcome.result,
        )

        self.specialists.register_outcome(
            dominant_specialist,
            decision.asset,
            str(decision.direction),
            regime,
            provider_root,
            decision.market_type,
            hour_bucket,
            decision.setup_quality,
            outcome.result,
        )

        self.store.upsert_collection_item(
            PENDING_COLLECTION,
            str(row.get("uid")),
            {**row, "status": "evaluated", "result": outcome.result, "evaluated_at_ts": time.time()},
        )

    def _liquidate_pending(self, snapshots: List[MarketSnapshot]) -> None:
        now_ts = time.time()
        for row in self._pending_rows():
            expires_at_ts = float(row.get("expires_at_ts", 0.0) or 0.0)
            if now_ts < expires_at_ts:
                continue
            snapshot = self._find_snapshot(snapshots, str(row.get("asset", "")))
            if not snapshot or len(snapshot.candles_m1) < 2:
                continue
            self._register_outcome(row, snapshot)

    def run_once(self, trigger: str = "manual") -> Dict[str, object]:
        with self._lock:
            self.runtime["meta"]["scan_in_progress"] = True  # type: ignore[index]
            started = time.time()

            snapshots = self.scanner.scan_assets()
            self._liquidate_pending(snapshots)

            capital = self.capital_service.get()
            decisions = [self.decision_engine.decide(snapshot, capital) for snapshot in snapshots]
            decisions.sort(key=lambda item: (item.score, item.confidence), reverse=True)

            current = decisions[0] if decisions else None
            signals = [self.signal_engine.to_payload(current)] if current and current.direction and current.execution_permission != "BLOQUEADO" else []

            self._schedule_pending(current)

            history = self.runtime.get("history", [])
            if current:
                history = [current.to_dict(), *history][:40]

            meta = self.runtime["meta"]  # type: ignore[assignment]
            meta["last_scan"] = now_brazil().strftime("%H:%M:%S")
            meta["scan_count"] = int(meta.get("scan_count", 0) or 0) + 1
            meta["signal_count"] = len(signals)
            meta["asset_count"] = len(snapshots)
            meta["scan_in_progress"] = False
            meta["last_scan_age_seconds"] = 0
            meta["last_scan_duration_ms"] = int((time.time() - started) * 1000)
            meta["last_scan_trigger"] = trigger

            self.runtime["signals"] = signals
            self.runtime["history"] = history
            self.runtime["current_decision"] = current.to_dict() if current else {}

            return {
                "ok": True,
                "signals": len(signals),
                "decision": current.to_dict() if current else {},
                "trigger": trigger,
            }

    def snapshot(self) -> Dict[str, object]:
        return self.runtime

    def _loop(self):
        while True:
            try:
                self.run_once("loop")
            except Exception:
                pass
            time.sleep(max(15, SETTINGS.scan_interval_seconds))

    def ensure_started(self):
        if self._started or not SETTINGS.run_background_scanner:
            return
        threading.Thread(target=self._loop, daemon=True).start()
        self._started = True
