from __future__ import annotations

import threading
import time
from typing import Dict, List

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.result_engine import ResultEngine
from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.intelligence.decision_engine import DecisionEngine
from alpha_hive.intelligence.signal_engine import SignalEngine
from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine
from alpha_hive.market.scanner import MarketScanner
from alpha_hive.services.capital_service import CapitalService

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

    def _register_outcome(self, decision, snapshot):
        if decision.direction not in ("CALL", "PUT"):
            return
        outcome = self.result_engine.evaluate_expired_decision(decision, snapshot.candles_m1[-2:])
        if not outcome:
            return
        dominant_specialist = decision.council.get("top_specialists", ["unknown"])[0] if decision.council else "unknown"
        payload = {
            **outcome.to_dict(),
            "asset": decision.asset,
            "provider": decision.provider,
            "state": decision.state,
            "dominant_specialist": dominant_specialist,
        }
        self.audit.record_trade(payload)
        hour_bucket = f"{now_brazil().hour:02d}:00"
        self.learning.register_outcome(decision.asset, decision.direction, decision.features.get("regime", "unknown"), dominant_specialist, decision.provider.split("-")[0], decision.market_type, hour_bucket, decision.setup_quality, outcome.result)
        self.specialists.register_outcome(dominant_specialist, decision.asset, decision.direction, decision.features.get("regime", "unknown"), decision.provider.split("-")[0], decision.market_type, hour_bucket, decision.setup_quality, outcome.result)

    def run_once(self, trigger: str = "manual") -> Dict[str, object]:
        with self._lock:
            self.runtime["meta"]["scan_in_progress"] = True  # type: ignore[index]
            started = time.time()
            snapshots = self.scanner.scan_assets()
            capital = self.capital_service.get()
            decisions = [self.decision_engine.decide(snapshot, capital) for snapshot in snapshots]
            decisions.sort(key=lambda item: (item.score, item.confidence), reverse=True)
            current = decisions[0] if decisions else None
            signals = [self.signal_engine.to_payload(d) for d in decisions if d.direction and d.execution_permission != "BLOQUEADO"][:3]
            if current:
                matched = next((snap for snap in snapshots if snap.asset == current.asset), None)
                if matched:
                    self._register_outcome(current, matched)
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
            return {"ok": True, "signals": len(signals), "decision": current.to_dict() if current else {}, "trigger": trigger}

    def snapshot(self) -> Dict[str, object]:
        meta = self.runtime["meta"]  # type: ignore[assignment]
        if meta.get("last_scan") != "--":
            last_duration = int(meta.get("last_scan_duration_ms", 0) or 0)
            meta["last_scan_age_seconds"] = max(0, int((time.time() - (time.time() - last_duration / 1000.0))))
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
