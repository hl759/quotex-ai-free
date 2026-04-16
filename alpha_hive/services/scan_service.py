from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.audit.result_engine import ResultEngine
from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import FinalDecision, MarketSnapshot
from alpha_hive.intelligence.decision_engine import DecisionEngine
from alpha_hive.intelligence.meta_decision_engine import MetaDecisionEngine
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
        self.meta_engine = MetaDecisionEngine()
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

    def _build_pending_payload(self, decision: FinalDecision, shadow_only: bool = False, selection_rank: int = 0) -> Dict[str, Any]:
        base = now_brazil().replace(second=0, microsecond=0)
        entry_epoch = base.timestamp() + 60
        expiration_epoch = base.timestamp() + 120
        analysis_key = base.strftime("%Y%m%d%H%M")
        direction = str(decision.direction or "NA")
        uid = f"{decision.asset}-{direction}-{analysis_key}-{'shadow' if shadow_only else 'live'}"
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
            "specialist_votes": decision.specialist_votes,
            "analysis_time": base.strftime("%H:%M"),
            "analysis_hour_bucket": base.strftime("%H:00"),
            "entry_time": time.strftime("%H:%M", time.localtime(entry_epoch)),
            "expiration": time.strftime("%H:%M", time.localtime(expiration_epoch)),
            "created_at_ts": time.time(),
            "expires_at_ts": expiration_epoch,
            "shadow_only": shadow_only,
            "selection_rank": selection_rank,
            "meta_rank_score": decision.meta_rank_score,
            "meta_state": decision.meta_state,
            "meta_reasons": decision.meta_reasons,
        }

    def _schedule_pending(self, decision: Optional[FinalDecision]) -> None:
        if not decision or decision.direction not in ("CALL", "PUT"):
            return
        if decision.execution_permission == "BLOQUEADO":
            return
        payload = self._build_pending_payload(decision, shadow_only=False, selection_rank=0)
        self.store.upsert_collection_item(PENDING_COLLECTION, payload["uid"], payload)

    def _schedule_shadows(self, ranked: List[FinalDecision]) -> None:
        shadow_rank = 1
        for candidate in ranked[1:4]:
            if candidate.direction not in ("CALL", "PUT"):
                continue
            if candidate.meta_rank_score < 4.9:
                continue
            payload = self._build_pending_payload(candidate, shadow_only=True, selection_rank=shadow_rank)
            self.store.upsert_collection_item(PENDING_COLLECTION, payload["uid"], payload)
            shadow_rank += 1

    def _pending_rows(self) -> List[Dict[str, Any]]:
        rows = self.store.list_collection(PENDING_COLLECTION, limit=400)
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
            specialist_votes=list(row.get("specialist_votes", []) or []),
            council=dict(row.get("council", {}) or {}),
            risk={},
            features=dict(row.get("features", {}) or {}),
            meta_rank_score=float(row.get("meta_rank_score", 0.0) or 0.0),
            meta_state=str(row.get("meta_state", "neutral")),
            meta_reasons=list(row.get("meta_reasons", []) or []),
        )

    def _hour_bucket_from_row(self, row: Dict[str, Any]) -> str:
        bucket = str(row.get("analysis_hour_bucket", "") or "").strip()
        if bucket and ":" in bucket:
            return f"{bucket.split(':')[0].zfill(2)}:00"
        analysis_time = str(row.get("analysis_time", "") or "").strip()
        if analysis_time and ":" in analysis_time:
            return f"{analysis_time.split(':')[0].zfill(2)}:00"
        return now_brazil().strftime("%H:00")

    def _learning_context(self, decision: FinalDecision, row: Dict[str, Any]) -> Dict[str, Any]:
        features = dict(decision.features or {})
        trend_m1 = str(features.get("trend_m1", "unknown"))
        trend_m5 = str(features.get("trend_m5", "unknown"))
        return {
            "trend_m1": trend_m1,
            "trend_m5": trend_m5,
            "multi_tf_conflict": trend_m1 != trend_m5,
            "breakout_quality": features.get("breakout_quality", "unknown"),
            "rejection_quality": features.get("rejection_quality", "unknown"),
            "explosive_expansion": bool(features.get("explosive_expansion", False)),
            "late_entry_risk": bool(features.get("late_entry_risk", False)),
            "is_sideways": bool(features.get("is_sideways", False)),
            "trend_quality_signal": features.get("trend_quality_signal", "unknown"),
            "consensus_quality": row.get("consensus_quality") or decision.consensus_quality,
        }

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "sim")

    def _specialist_merit(self, vote: Dict[str, Any], decision: FinalDecision, outcome) -> Tuple[str, float, str] | None:
        specialist = str(vote.get("specialist", "") or "").strip()
        specialist_direction = str(vote.get("direction", "") or "").strip()
        setup_quality = str(vote.get("setup_quality", decision.setup_quality) or decision.setup_quality)
        confidence = int(vote.get("confidence", 50) or 50)
        market_fit = float(vote.get("market_fit", 0.0) or 0.0)
        veto = self._truthy(vote.get("veto", False))

        if not specialist:
            return None

        base_weight = max(0.35, min(1.20, 0.45 + (market_fit * 0.45) + max(0, confidence - 50) / 100.0))
        features = dict(decision.features or {})
        sideways = bool(features.get("is_sideways", False))
        clean_trend = str(features.get("trend_m1", "unknown")) == str(features.get("trend_m5", "unknown")) and not sideways

        if veto:
            if outcome.result == "LOSS" or outcome.loss_cause in (
                "wrong_direction",
                "conflict_ignored",
                "regime_transition",
                "volatility_trap",
                "breakout_exhaustion",
            ):
                return "WIN", min(1.15, base_weight), "correct_veto"
            return "LOSS", min(0.55, base_weight), "unnecessary_veto"

        if specialist_direction not in ("CALL", "PUT"):
            return None

        if specialist_direction == str(decision.direction):
            if outcome.result == "WIN":
                if sideways and specialist in ("mean_reversion", "reversal", "regime"):
                    merit = "good_sideways_reading"
                elif clean_trend and specialist in ("trend", "breakout", "regime", "session"):
                    merit = "good_trend_reading"
                elif setup_quality == "premium" or market_fit >= 0.80:
                    merit = "high_quality_contribution"
                else:
                    merit = "aligned_good_consensus"
                return "WIN", min(1.20, base_weight), merit

            if outcome.loss_cause in (
                "late_entry",
                "overextended_move",
                "followthrough_failure",
                "timing_degradation",
            ):
                return "LOSS", max(0.30, min(0.55, base_weight * 0.55)), "correct_direction_bad_timing"
            if outcome.loss_cause == "conflict_ignored":
                return "LOSS", min(1.10, base_weight), "conflict_ignored"
            if outcome.loss_cause == "breakout_exhaustion" and specialist == "breakout":
                return "LOSS", min(1.10, base_weight), "breakout_chase_failure"
            if outcome.loss_cause == "reversal_ignored" and specialist in ("trend", "breakout", "timing"):
                return "LOSS", min(1.00, base_weight), "reversal_without_proof"
            if outcome.loss_cause == "regime_transition":
                return "LOSS", min(1.00, base_weight), "regime_transition_misread"
            return "LOSS", min(1.20, base_weight), "wrong_direction"

        if outcome.reverse_would_win and specialist_direction == outcome.reverse_direction:
            merit = "good_sideways_reading" if sideways and specialist in ("mean_reversion", "reversal", "regime") else "counterfactual_correct_direction"
            return "WIN", min(1.00, base_weight * 0.95), merit

        if outcome.result == "WIN":
            return "LOSS", min(0.85, base_weight), "aligned_bad_consensus"

        return "LOSS", max(0.30, min(0.60, base_weight * 0.70)), "structurally_fragile_contribution"

    def _register_outcome(self, row: Dict[str, Any], snapshot: MarketSnapshot) -> None:
        decision = self._decision_from_pending(row)
        outcome = self.result_engine.evaluate_expired_decision(decision, snapshot.candles_m1[-5:])
        if not outcome:
            return

        dominant_specialist = str(row.get("dominant_specialist", "unknown"))
        regime = str(decision.features.get("regime", "unknown"))
        provider_root = str(decision.provider or "unknown").split("-")[0]
        hour_bucket = self._hour_bucket_from_row(row)
        learning_context = self._learning_context(decision, row)
        shadow_only = self._truthy(row.get("shadow_only", False))

        if not shadow_only:
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
                "hour_bucket": hour_bucket,
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
                loss_cause=outcome.loss_cause,
                reverse_would_win=outcome.reverse_would_win,
                counterfactual_better=outcome.counterfactual_better,
                entry_efficiency=outcome.entry_efficiency,
                operating_state=decision.state,
                signal_type=decision.decision,
                extra_context=learning_context,
            )

        self.learning.register_opportunity_feedback(
            asset=decision.asset,
            direction=str(decision.direction),
            regime=regime,
            provider=provider_root,
            market_type=decision.market_type,
            hour_bucket=hour_bucket,
            setup_quality=decision.setup_quality,
            result=outcome.result,
            selected=not shadow_only,
            extra_context=learning_context,
        )

        seen_specialists = set()
        specialist_votes = list(row.get("specialist_votes", []) or [])

        for vote in specialist_votes:
            specialist = str(vote.get("specialist", "") or "").strip()
            if not specialist or specialist in seen_specialists:
                continue

            merit = self._specialist_merit(vote, decision, outcome)
            if merit is None:
                continue

            specialist_result, specialist_weight, merit_mode = merit
            specialist_direction = str(vote.get("direction") or decision.direction or "CALL")
            specialist_setup = str(vote.get("setup_quality") or decision.setup_quality)

            self.specialists.register_outcome(
                specialist,
                decision.asset,
                specialist_direction,
                regime,
                provider_root,
                decision.market_type,
                hour_bucket,
                specialist_setup,
                specialist_result,
                weight=specialist_weight,
                merit_mode=merit_mode,
                extra_context=learning_context,
            )
            seen_specialists.add(specialist)

        if not seen_specialists and not shadow_only:
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
                weight=1.0,
                merit_mode="standard",
                extra_context=learning_context,
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
            audit_report = self.audit.compute_report()

            ranked_decisions: List[FinalDecision] = []
            for snapshot in snapshots:
                decision = self.decision_engine.decide(snapshot, capital)
                adjusted = self.meta_engine.validate(decision, snapshot, audit_report)
                ranked_decisions.append(adjusted)

            ranked_decisions.sort(key=lambda item: (item.meta_rank_score, item.score, item.confidence), reverse=True)

            current = ranked_decisions[0] if ranked_decisions else None
            signals = [self.signal_engine.to_payload(current)] if current and current.direction and current.execution_permission != "BLOQUEADO" else []

            self._schedule_pending(current)
            self._schedule_shadows(ranked_decisions)

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
