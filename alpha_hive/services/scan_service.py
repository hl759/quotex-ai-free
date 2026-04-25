from __future__ import annotations

import gc
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import FinalDecision, MarketSnapshot
from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.learning.specialist_reputation_engine import SpecialistReputationEngine
from alpha_hive.market.scanner import MarketScanner
from alpha_hive.services.capital_service import CapitalService
from alpha_hive.storage.state_store import get_state_store

# DecisionEngine, MetaDecisionEngine, SignalEngine, ResultEngine são importados
# de forma lazy dentro de run_once() — não ficam em RAM fora da sessão de scan.

PENDING_COLLECTION = "pending_signals_v2"


class ScanService:
    def __init__(self):
        # Scanner direto — sem PassiveWatcher. Dados buscados frescos a cada ciclo
        # e liberados imediatamente após o scan. Zero buffers de velas em RAM.
        self.scanner = MarketScanner()

        self.capital_service = CapitalService()
        self.learning = LearningEngine()
        self.specialists = SpecialistReputationEngine()
        self.audit = EdgeAuditEngine()
        self.journal = JournalManager()
        self.store = get_state_store()

        # ENGINES STATELESS — NÃO instanciados aqui. São criados em run_once()
        # e destruídos ao final de cada scan para liberar RAM imediatamente.
        # DecisionEngine (9 especialistas + FeatureEngine + CouncilEngine + EdgeGuard)
        # MetaDecisionEngine, SignalEngine, ResultEngine são todos stateless.

        self.runtime: Dict[str, object] = {
            "signals": [],
            "history": [],
            "current_decision": {},
            "meta": {
                "last_scan": "--",
                "last_scan_ts": 0.0,
                "scan_count": 0,
                "signal_count": 0,
                "asset_count": 0,
                "scan_in_progress": False,
                "last_scan_age_seconds": 0,
                "last_scan_error": "",
                "pending_total": 0,
                "pending_expired": 0,
                "pending_evaluated_last_scan": 0,
                "ui_auto_refresh_seconds": SETTINGS.ui_auto_refresh_seconds,
                "ui_stale_after_seconds": SETTINGS.ui_stale_after_seconds,
                "ui_force_scan_after_seconds": SETTINGS.ui_force_scan_after_seconds,
            },
        }
        self._lock = threading.Lock()
        self._started = False
        self._last_activity_ts: float = 0.0
        self._restore_runtime()

    def _meta(self) -> Dict[str, Any]:
        return self.runtime.setdefault("meta", {})  # type: ignore[return-value]

    def _scan_age_seconds(self, now_ts: Optional[float] = None) -> int:
        now_ts = now_ts or time.time()
        meta = self._meta()
        last_scan_ts = float(meta.get("last_scan_ts", 0.0) or 0.0)
        if last_scan_ts <= 0:
            return 0
        return max(0, int(now_ts - last_scan_ts))

    def _restore_runtime(self) -> None:
        """Restaura apenas histórico do PostgreSQL — sinais e decisão começam vazios."""
        try:
            saved = self.store.get_json("scan_runtime_v1", {})
            if not saved:
                return
            # Restaura só o histórico; sinais e current_decision ficam em branco
            # até o usuário clicar em "Atualizar agora".
            if "history" in saved:
                self.runtime["history"] = saved["history"]

            saved_meta = saved.get("meta", {})
            if saved_meta:
                meta = self._meta()
                meta.update(saved_meta)
                meta["scan_in_progress"] = False
                meta["ui_auto_refresh_seconds"] = SETTINGS.ui_auto_refresh_seconds
                meta["ui_stale_after_seconds"] = SETTINGS.ui_stale_after_seconds
                meta["ui_force_scan_after_seconds"] = SETTINGS.ui_force_scan_after_seconds
            log.info("ScanService: runtime restaurado do PostgreSQL")
        except Exception as exc:
            log.warning("ScanService: falha ao restaurar runtime (%s) — iniciando vazio", exc)

    def _persist_runtime(self) -> None:
        """Persiste runtime no PostgreSQL após cada scan — sobrevive a restarts do Render."""
        try:
            meta = {k: v for k, v in self._meta().items() if k != "scan_in_progress"}
            self.store.set_json("scan_runtime_v1", {
                "signals": self.runtime.get("signals", []),
                "history": (self.runtime.get("history", []) or [])[:20],
                "current_decision": self.runtime.get("current_decision", {}),
                "meta": meta,
            })
        except Exception as exc:
            log.warning("ScanService: falha ao persistir runtime (%s)", exc)

    def _find_snapshot(self, snapshots: List[MarketSnapshot], asset: str) -> Optional[MarketSnapshot]:
        return next((snap for snap in snapshots if snap.asset == asset), None)

    def _pending_rows(self) -> List[Dict[str, Any]]:
        rows = self.store.list_collection(PENDING_COLLECTION, limit=400)
        return [row for row in rows if str(row.get("status", "pending")) == "pending"]

    def _count_pending_state(self) -> Tuple[int, int]:
        now_ts = time.time()
        rows = self._pending_rows()
        expired = 0
        for row in rows:
            expires_at_ts = float(row.get("expires_at_ts", 0.0) or 0.0)
            if expires_at_ts > 0 and now_ts >= expires_at_ts:
                expired += 1
        return len(rows), expired

    def _planned_signal_window(self, analysis_ts: Optional[float] = None) -> Dict[str, Any]:
        analysis_ts = float(analysis_ts or time.time())
        now_local = now_brazil()
        min_lead = max(8, int(getattr(SETTINGS, "signal_min_lead_seconds", 18) or 18))
        target_epoch = max(analysis_ts + min_lead, now_local.timestamp() + min_lead)
        entry_epoch = int(((target_epoch + 59) // 60) * 60)
        expiration_epoch = entry_epoch + 60
        tz = now_local.tzinfo
        entry_dt = datetime.fromtimestamp(entry_epoch, tz=tz)
        expiration_dt = datetime.fromtimestamp(expiration_epoch, tz=tz)
        return {
            "analysis_ts": analysis_ts,
            "analysis_time": now_local.strftime("%H:%M"),
            "analysis_time_exact": now_local.strftime("%H:%M:%S"),
            "entry_ts": entry_epoch,
            "entry_time": entry_dt.strftime("%H:%M"),
            "expiration_ts": expiration_epoch,
            "expiration": expiration_dt.strftime("%H:%M"),
            "lead_seconds": max(0, int(entry_epoch - analysis_ts)),
        }

    def _is_operable_candidate(self, decision: Optional[FinalDecision]) -> bool:
        if not decision:
            return False
        return bool(
            decision.direction in ("CALL", "PUT")
            and decision.execution_permission in ("LIBERADO", "CAUTELA_OPERAVEL")
            and decision.decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA")
        )

    def _decorate_signal_payload(self, payload: Dict[str, Any], planned: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(payload)
        out.update(
            {
                "analysis_time": planned["analysis_time"],
                "analysis_time_exact": planned["analysis_time_exact"],
                "analysis_ts": planned["analysis_ts"],
                "entry_time": planned["entry_time"],
                "entry_ts": planned["entry_ts"],
                "expiration": planned["expiration"],
                "expiration_ts": planned["expiration_ts"],
                "lead_seconds": planned["lead_seconds"],
            }
        )
        return out

    def _decorate_current_decision(self, decision: Optional[FinalDecision], planned: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not decision:
            return {}
        out = decision.to_dict()
        if planned and self._is_operable_candidate(decision):
            out.update(
                {
                    "analysis_time": planned["analysis_time"],
                    "analysis_time_exact": planned["analysis_time_exact"],
                    "analysis_ts": planned["analysis_ts"],
                    "entry_time": planned["entry_time"],
                    "entry_ts": planned["entry_ts"],
                    "expiration": planned["expiration"],
                    "expiration_ts": planned["expiration_ts"],
                    "lead_seconds": planned["lead_seconds"],
                }
            )
        else:
            # Para decisões não-operáveis (OBSERVAR/BLOQUEADO), registra o horário
            # da análise para que o usuário saiba que o scan foi executado agora.
            analysis_time = (planned or {}).get("analysis_time") or now_brazil().strftime("%H:%M")
            out["analysis_time"] = analysis_time
            out.setdefault("entry_time", "--:--")
            out.setdefault("expiration", "--:--")
            out.setdefault("lead_seconds", 0)
        return out

    def _build_pending_payload(self, decision: FinalDecision, planned: Optional[Dict[str, Any]] = None, shadow_only: bool = False, selection_rank: int = 0) -> Dict[str, Any]:
        analysis_ts = time.time()
        planned = planned or self._planned_signal_window(analysis_ts=analysis_ts)

        slot_key = datetime.fromtimestamp(planned["entry_ts"], tz=now_brazil().tzinfo).strftime("%Y%m%d%H%M")
        fingerprint = "-".join(
            [
                str(decision.asset or "NA"),
                str(decision.direction or "NA"),
                str(decision.decision or "OBSERVAR"),
                str(decision.setup_quality or "monitorado"),
                str(decision.consensus_quality or "split"),
                "shadow" if shadow_only else "live",
            ]
        )
        uid = f"{slot_key}-{fingerprint}"

        dominant_specialist = decision.council.get("top_specialists", ["unknown"])[0] if decision.council else "unknown"
        features = dict(decision.features or {})
        return {
            "uid": uid,
            "status": "pending",
            "asset": decision.asset,
            "decision": decision.decision,
            "direction": decision.direction,
            "provider": decision.provider,
            "provider_at_signal": decision.provider,
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
            "analysis_time": planned["analysis_time"],
            "analysis_time_exact": planned["analysis_time_exact"],
            "analysis_hour_bucket": planned["analysis_time"][:2] + ":00",
            "analysis_ts": planned["analysis_ts"],
            "entry_time": planned["entry_time"],
            "entry_ts": planned["entry_ts"],
            "expiration": planned["expiration"],
            "expiration_ts": planned["expiration_ts"],
            "created_at_ts": planned["analysis_ts"],
            "expires_at_ts": planned["expiration_ts"],
            "lead_seconds": planned["lead_seconds"],
            "shadow_only": shadow_only,
            "selection_rank": selection_rank,
            "meta_rank_score": decision.meta_rank_score,
            "meta_state": decision.meta_state,
            "meta_reasons": decision.meta_reasons,
            "source_symbol_at_signal": str(features.get("source_symbol", "") or ""),
            "source_kind_at_signal": str(features.get("source_kind", "standard") or "standard"),
        }

    def _schedule_pending(self, decision: Optional[FinalDecision], planned: Optional[Dict[str, Any]] = None) -> None:
        if not self._is_operable_candidate(decision):
            return

        payload = self._build_pending_payload(decision, planned=planned, shadow_only=False, selection_rank=0)
        existing = self.store.get_collection_item(PENDING_COLLECTION, payload["uid"], None)
        if isinstance(existing, dict) and str(existing.get("status", "pending")) == "pending":
            return

        self.store.upsert_collection_item(PENDING_COLLECTION, payload["uid"], payload)

    def _schedule_shadows(self, ranked: List[FinalDecision]) -> None:
        shadow_rank = 1
        for candidate in ranked[:3]:
            if not self._is_operable_candidate(candidate):
                continue
            if candidate.meta_rank_score < 4.9:
                continue

            payload = self._build_pending_payload(candidate, shadow_only=True, selection_rank=shadow_rank)
            existing = self.store.get_collection_item(PENDING_COLLECTION, payload["uid"], None)
            if isinstance(existing, dict) and str(existing.get("status", "pending")) == "pending":
                shadow_rank += 1
                continue

            self.store.upsert_collection_item(PENDING_COLLECTION, payload["uid"], payload)
            shadow_rank += 1

    def _has_expired_pending(self, now_ts: Optional[float] = None) -> bool:
        now_ts = now_ts or time.time()
        for row in self._pending_rows():
            expires_at_ts = float(row.get("expires_at_ts", 0.0) or 0.0)
            if expires_at_ts > 0 and now_ts >= expires_at_ts:
                return True
        return False

    def should_auto_scan(self) -> bool:
        meta = self._meta()
        if bool(meta.get("scan_in_progress", False)):
            return False

        now_ts = time.time()
        scan_count = int(meta.get("scan_count", 0) or 0)
        scan_age = self._scan_age_seconds(now_ts)

        if scan_count <= 0:
            return True

        if self._has_expired_pending(now_ts):
            return True

        if scan_age >= max(15, SETTINGS.scan_interval_seconds):
            return True

        return False

    def auto_refresh_if_needed(self, trigger: str = "snapshot_auto") -> Dict[str, object]:
        if self.should_auto_scan():
            return self.run_once(trigger)
        return {"ok": True, "skipped": True, "reason": "fresh_enough"}

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

    def _register_outcome(self, row: Dict[str, Any], snapshot: MarketSnapshot) -> bool:
        decision = self._decision_from_pending(row)

        analysis_ts = float(row.get("analysis_ts", row.get("created_at_ts", 0.0)) or 0.0)
        entry_ts = float(row.get("entry_ts", 0.0) or 0.0)
        expiration_ts = float(row.get("expiration_ts", row.get("expires_at_ts", 0.0)) or 0.0)
        delay_seconds = max(0, int(time.time() - expiration_ts)) if expiration_ts > 0 else 0

        result_engine = getattr(self, "_scan_result_engine", None)
        if result_engine is None:
            from alpha_hive.audit.result_engine import ResultEngine
            result_engine = ResultEngine()
        outcome = result_engine.evaluate_expired_decision(
            decision=decision,
            candles=snapshot.candles_m1,
            analysis_ts=analysis_ts if analysis_ts > 0 else None,
            entry_ts=entry_ts if entry_ts > 0 else None,
            expiration_ts=expiration_ts if expiration_ts > 0 else None,
            delay_seconds=delay_seconds,
        )
        if not outcome:
            return False

        dominant_specialist = str(row.get("dominant_specialist", "unknown"))
        regime = str(decision.features.get("regime", "unknown"))
        provider_root = str(decision.provider or "unknown").split("-")[0]
        hour_bucket = self._hour_bucket_from_row(row)
        learning_context = self._learning_context(decision, row)
        shadow_only = self._truthy(row.get("shadow_only", False))

        if not shadow_only:
            payload = {
                **outcome.to_dict(),
                "uid": str(outcome.uid),
                "asset": decision.asset,
                "signal": decision.direction,
                "direction": decision.direction,
                "provider": decision.provider,
                "provider_at_signal": row.get("provider_at_signal", decision.provider),
                "state": decision.state,
                "dominant_specialist": dominant_specialist,
                "analysis_time": row.get("analysis_time"),
                "analysis_time_exact": row.get("analysis_time_exact"),
                "analysis_ts": analysis_ts,
                "signal_analysis_ts": outcome.signal_analysis_ts,
                "entry_time": row.get("entry_time"),
                "entry_ts": entry_ts,
                "signal_entry_ts": outcome.signal_entry_ts,
                "expiration": row.get("expiration"),
                "expiration_ts": expiration_ts,
                "signal_expiration_ts": outcome.signal_expiration_ts,
                "entry_candle_ts": outcome.entry_candle_ts,
                "exit_candle_ts": outcome.exit_candle_ts,
                "evaluated_at_ts": outcome.evaluated_at_ts,
                "hour_bucket": hour_bucket,
                "setup_quality": decision.setup_quality,
                "regime": regime,
                "risk_pct": decision.risk_pct,
                "score": decision.score,
                "confidence": decision.confidence,
                "source_symbol_at_signal": row.get("source_symbol_at_signal", ""),
                "source_kind_at_signal": row.get("source_kind_at_signal", "standard"),
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
            {
                **row,
                "status": "evaluated",
                "result": outcome.result,
                "evaluated_at_ts": outcome.evaluated_at_ts or time.time(),
                "entry_candle_ts": outcome.entry_candle_ts,
                "exit_candle_ts": outcome.exit_candle_ts,
                "evaluation_mode": outcome.evaluation_mode,
            },
        )
        return True

    def _snapshot_for_pending(
        self,
        asset: str,
        snapshot_map: Dict[str, MarketSnapshot],
    ) -> Optional[MarketSnapshot]:
        cached = snapshot_map.get(asset)
        if cached and len(cached.candles_m1) >= 2:
            return cached

        try:
            one_off = self.scanner.scan_asset(asset)
        except Exception:
            one_off = None

        if one_off and len(one_off.candles_m1) >= 2:
            snapshot_map[asset] = one_off
            return one_off
        return None

    def _liquidate_pending(self, snapshots: List[MarketSnapshot]) -> int:
        now_ts = time.time()
        snapshot_map = {snap.asset: snap for snap in snapshots}
        evaluated = 0

        for row in self._pending_rows():
            expires_at_ts = float(row.get("expires_at_ts", 0.0) or 0.0)
            if expires_at_ts <= 0 or now_ts < expires_at_ts:
                continue

            asset = str(row.get("asset", "") or "").strip()
            if not asset:
                self.store.upsert_collection_item(
                    PENDING_COLLECTION,
                    str(row.get("uid")),
                    {**row, "status": "discarded", "discard_reason": "missing_asset", "evaluated_at_ts": now_ts},
                )
                continue

            snapshot = self._snapshot_for_pending(asset, snapshot_map)
            if not snapshot:
                continue

            if self._register_outcome(row, snapshot):
                evaluated += 1

        return evaluated

    def run_once(self, trigger: str = "manual") -> Dict[str, object]:
        with self._lock:
            meta = self._meta()
            started = time.time()
            self._last_activity_ts = started
            meta["scan_in_progress"] = True
            meta["last_scan_error"] = ""
            _decision_engine = None
            _meta_engine = None
            _signal_engine = None
            self._scan_result_engine = None

            try:
                from alpha_hive.intelligence.decision_engine import DecisionEngine
                from alpha_hive.intelligence.meta_decision_engine import MetaDecisionEngine
                from alpha_hive.intelligence.signal_engine import SignalEngine
                from alpha_hive.audit.result_engine import ResultEngine

                _decision_engine = DecisionEngine(
                    learning_engine=self.learning,
                    audit_engine=self.audit,
                    reputation_engine=self.specialists,
                )
                _meta_engine = MetaDecisionEngine(learning_engine=self.learning)
                _signal_engine = SignalEngine()
                self._scan_result_engine = ResultEngine()

                snapshots = self.scanner.scan_assets()

                # Filtra apenas ativos com candles suficientes para análise significativa.
                # Assets que retornaram dados parciais ou sem histórico mínimo são descartados.
                snapshots = [s for s in snapshots if len(s.candles_m1) >= 5]

                # Registra horário do scan logo após os dados serem buscados.
                # Assim mesmo que a fase de decisão falhe, o usuário vê dados frescos.
                fetch_ts = time.time()
                meta["last_scan"] = now_brazil().strftime("%H:%M:%S")
                meta["last_scan_ts"] = fetch_ts
                meta["asset_count"] = len(snapshots)
                meta["last_scan_age_seconds"] = 0

                evaluated_count = self._liquidate_pending(snapshots)

                capital = self.capital_service.get()
                audit_report = self.audit.compute_report()

                ranked_decisions: List[FinalDecision] = []
                for snapshot in snapshots:
                    decision = _decision_engine.decide(
                        snapshot=snapshot,
                        capital_state=capital,
                        audit_summary=audit_report,
                    )
                    adjusted = _meta_engine.validate(decision, snapshot, audit_report)
                    ranked_decisions.append(adjusted)

                ranked_decisions.sort(key=lambda item: (item.meta_rank_score, item.score, item.confidence), reverse=True)
                t_decision_done = time.time()

                current_analysis = ranked_decisions[0] if ranked_decisions else None
                primary_signal = next((item for item in ranked_decisions if self._is_operable_candidate(item)), None)
                # Sempre computa planned para incluir analysis_time mesmo em decisões OBSERVAR/BLOQUEADO.
                planned = self._planned_signal_window(analysis_ts=time.time())

                signals: List[Dict[str, Any]] = []
                if primary_signal:
                    signals = [self._decorate_signal_payload(_signal_engine.to_payload(primary_signal), planned)]

                self._schedule_pending(primary_signal, planned=planned if primary_signal else None)
                operable_followups = [item for item in ranked_decisions if item is not primary_signal and self._is_operable_candidate(item)]
                self._schedule_shadows(operable_followups)

                current_payload = self._decorate_current_decision(primary_signal or current_analysis, planned=planned)

                history = self.runtime.get("history", [])
                if primary_signal:
                    history = [current_payload, *history][:40]
                elif current_analysis:
                    history = [self._decorate_current_decision(current_analysis), *history][:40]

                pending_total, pending_expired = self._count_pending_state()
                t_signal_done = time.time()
                finished_at = t_signal_done

                meta["scan_count"] = int(meta.get("scan_count", 0) or 0) + 1
                meta["signal_count"] = len(signals)
                meta["last_scan_duration_ms"] = int((finished_at - started) * 1000)
                meta["timing_fetch_ms"] = int((fetch_ts - started) * 1000)
                meta["timing_decision_ms"] = int((t_decision_done - fetch_ts) * 1000)
                meta["timing_signal_ms"] = int((t_signal_done - t_decision_done) * 1000)
                meta["last_scan_trigger"] = trigger
                meta["pending_total"] = pending_total
                meta["pending_expired"] = pending_expired
                meta["pending_evaluated_last_scan"] = evaluated_count

                log.info(
                    "ScanService[%s]: fetch=%dms | decisão=%dms | sinal=%dms | total=%dms"
                    " | ativos=%d | resultado=%s",
                    trigger,
                    meta["timing_fetch_ms"],
                    meta["timing_decision_ms"],
                    meta["timing_signal_ms"],
                    meta["last_scan_duration_ms"],
                    len(snapshots),
                    current_payload.get("decision", "?"),
                )

                self.runtime["signals"] = signals
                self.runtime["history"] = history
                self.runtime["current_decision"] = current_payload
                self._persist_runtime()


                return {
                    "ok": True,
                    "signals": len(signals),
                    "decision": current_payload,
                    "trigger": trigger,
                    "evaluated": evaluated_count,
                    "duration_ms": int((time.time() - started) * 1000),
                }
            except Exception as exc:
                err = repr(exc)
                meta["last_scan_error"] = err
                return {
                    "ok": False,
                    "error": err,
                    "trigger": trigger,
                    "duration_ms": int((time.time() - started) * 1000),
                }
            finally:
                if _decision_engine is not None:
                    del _decision_engine
                if _meta_engine is not None:
                    del _meta_engine
                if _signal_engine is not None:
                    del _signal_engine
                self._scan_result_engine = None
                meta["scan_in_progress"] = False
                self._release_market_memory()
                gc.collect()

    def snapshot(self) -> Dict[str, object]:
        meta = self._meta()
        pending_total, pending_expired = self._count_pending_state()
        meta["last_scan_age_seconds"] = self._scan_age_seconds()
        meta["pending_total"] = pending_total
        meta["pending_expired"] = pending_expired
        meta.setdefault("ui_auto_refresh_seconds", SETTINGS.ui_auto_refresh_seconds)
        meta.setdefault("ui_stale_after_seconds", SETTINGS.ui_stale_after_seconds)
        meta.setdefault("ui_force_scan_after_seconds", SETTINGS.ui_force_scan_after_seconds)
        meta.setdefault("last_scan_error", "")
        return self.runtime

    def _release_market_memory(self) -> None:
        """Libera cache HTTP do DataManager após cada ciclo."""
        try:
            self.scanner.data.clear_cache()
        except Exception:
            pass

    def maybe_cleanup_idle(self) -> None:
        """
        ESTADO B — limpeza por inatividade.
        Se nenhum scan foi feito nos últimos INACTIVITY_TIMEOUT_SECONDS, descarta
        o histórico extenso mantendo apenas os últimos 5 registros.
        Chamado passivamente no GET /snapshot (sem custo quando ativo).
        """
        timeout = int(getattr(SETTINGS, "inactivity_timeout_seconds", 600) or 600)
        age = self._scan_age_seconds()
        if age <= 0 or age < timeout:
            return
        history = self.runtime.get("history", [])
        if isinstance(history, list) and len(history) > 5:
            self.runtime["history"] = history[:5]
        gc.collect()

    def ensure_started(self):
        """Inicia o loop autônomo de scan em background."""
        if self._started:
            return
        self._started = True
        t = threading.Thread(target=self._background_loop, daemon=True, name="scan-loop")
        t.start()
        log.info("ScanService: loop autônomo iniciado (intervalo=%ds)", SETTINGS.scan_interval_seconds)

    def _background_loop(self):
        """Loop autônomo sincronizado com o fechamento do candle M1.

        Aguarda :02 de cada minuto (2 segundos após o fechamento em :00) para
        garantir que as APIs já disponibilizaram o candle fechado antes do scan.
        Isso evita analisar o candle ainda em formação como se fosse fechado.
        """
        while True:
            try:
                self.run_once("auto")
            except Exception as exc:
                log.warning("ScanService: erro no ciclo de scan (%s)", exc)
            finally:
                self.learning.release()
                self.specialists.release()
                gc.collect()

            # Calcula sleep até o :02 do próximo minuto (2s após fechamento M1).
            now = time.time()
            seconds_past = now % 60
            if seconds_past < 2.0:
                sleep_seconds = 2.0 - seconds_past
            else:
                sleep_seconds = 62.0 - seconds_past
            # Clamp de segurança: nunca esperar mais que o intervalo configurado
            sleep_seconds = max(1.0, min(float(SETTINGS.scan_interval_seconds), sleep_seconds))
            log.debug("ScanService: próximo scan M1 em %.1fs (alinhado ao fechamento)", sleep_seconds)
            time.sleep(sleep_seconds)
