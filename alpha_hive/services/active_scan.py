from __future__ import annotations
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
from alpha_hive.market.passive_watcher import AssetContext, PassiveWatcher
from alpha_hive.market.scanner import MarketScanner
from alpha_hive.services.capital_service import CapitalService
from alpha_hive.storage.state_store import get_state_store


def _market_type(asset: str) -> str:
    if asset in SETTINGS.assets_crypto or asset in SETTINGS.assets_pure_crypto:
        return "crypto"
    if asset in SETTINGS.assets_forex:
        return "forex"
    return "metals"


def _decorate_decision(decision: Optional[FinalDecision], planned: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not decision:
        return {}
    out = decision.to_dict()
    if planned and decision.direction in ("CALL", "PUT"):
        out.update(planned)
    else:
        out.setdefault("analysis_time", "--:--")
        out.setdefault("entry_time", "--:--")
        out.setdefault("expiration", "--:--")
        out.setdefault("lead_seconds", 0)
    return out


class ActiveScan:
    def __init__(self, passive_watcher: PassiveWatcher):
        self.passive = passive_watcher
        self.decision_engine = DecisionEngine()
        self.meta_engine = MetaDecisionEngine()
        self.signal_engine = SignalEngine()
        self.result_engine = ResultEngine()
        self.capital_service = CapitalService()
        self.learning = LearningEngine()
        self.specialists_rep = SpecialistReputationEngine()
        self.audit = EdgeAuditEngine()
        self.journal = JournalManager()
        self.scanner = MarketScanner()
        self.store = get_state_store()

    def _context_to_snapshot(self, ctx: AssetContext) -> Optional[MarketSnapshot]:
        candles_m1, candles_m5 = ctx.to_candle_lists()
        if len(candles_m1) < 12:
            return None
        return MarketSnapshot(
            asset=ctx.asset,
            market_type=_market_type(ctx.asset),
            provider=ctx.provider,
            provider_fallback_chain=ctx.provider_chain,
            data_quality_score=ctx.data_quality_score,
            data_quality_state=ctx.data_quality_state,
            candles_m1=candles_m1,
            candles_m5=candles_m5,
            warnings=ctx.warnings,
            display_asset=ctx.asset,
            source_symbol=ctx.source_symbol,
            source_kind=ctx.source_kind,
        )

    def _snapshots_from_passive(self) -> Tuple[List[MarketSnapshot], int, int]:
        contexts = self.passive.get_all_contexts()
        snapshots: List[MarketSnapshot] = []
        stale_count = 0
        asset_order = {asset: idx for idx, asset in enumerate(SETTINGS.assets)}
        for asset, ctx in contexts.items():
            if ctx.is_initialized and ctx.is_fresh:
                snap = self._context_to_snapshot(ctx)
                if snap:
                    snapshots.append(snap)
            else:
                stale_count += 1
                try:
                    snap = self.scanner.scan_asset(asset)
                    if snap:
                        snapshots.append(snap)
                except Exception:
                    pass
        snapshots.sort(key=lambda s: asset_order.get(s.asset, 10**9))
        return snapshots, len(contexts), stale_count

    @staticmethod
    def _is_operable(decision: Optional[FinalDecision]) -> bool:
        if not decision:
            return False
        return bool(
            decision.direction in ("CALL", "PUT")
            and decision.execution_permission in ("LIBERADO", "CAUTELA_OPERAVEL")
            and decision.decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA")
        )

    def _rank_all(self, snapshots: List[MarketSnapshot], capital: dict, audit_report: Dict[str, Any]) -> List[FinalDecision]:
        ranked: List[FinalDecision] = []
        for snapshot in snapshots:
            try:
                decision = self.decision_engine.decide(snapshot=snapshot, capital_state=capital, audit_summary=audit_report)
                adjusted = self.meta_engine.validate(decision, snapshot, audit_report)
                ranked.append(adjusted)
            except Exception:
                continue
        ranked.sort(key=lambda d: (d.meta_rank_score, d.score, d.confidence), reverse=True)
        return ranked

    @staticmethod
    def _planned_signal_window(analysis_ts: Optional[float] = None) -> Dict[str, Any]:
        from datetime import datetime
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

    def execute(self) -> Dict[str, Any]:
        started = time.time()
        snapshots, total_assets, stale_count = self._snapshots_from_passive()
        if not snapshots:
            return {"ok": False, "error": "no_data", "duration_ms": int((time.time() - started) * 1000)}
        capital = self.capital_service.get()
        audit_report = self.audit.compute_report()
        ranked = self._rank_all(snapshots, capital, audit_report)
        primary = next((d for d in ranked if self._is_operable(d)), None)
        top_decision = primary or (ranked[0] if ranked else None)
        planned = self._planned_signal_window(analysis_ts=started) if primary else None
        signal_payload: Optional[Dict[str, Any]] = None
        if primary and planned:
            raw = self.signal_engine.to_payload(primary)
            signal_payload = {**raw, **planned}
        current_decision = _decorate_decision(top_decision, planned)
        top5 = [
            {"rank": i+1, "asset": d.asset, "direction": d.direction, "decision": d.decision,
             "meta_rank_score": round(d.meta_rank_score, 3), "score": round(d.score, 3),
             "confidence": d.confidence, "execution_permission": d.execution_permission}
            for i, d in enumerate(ranked[:5])
        ]
        return {
            "ok": True,
            "signal": signal_payload,
            "current_decision": current_decision,
            "ranked_top5": top5,
            "assets_scanned": len(snapshots),
            "assets_total": total_assets,
            "assets_stale": stale_count,
            "operable_found": primary is not None,
            "analysis_time": now_brazil().strftime("%H:%M:%S"),
            "duration_ms": int((time.time() - started) * 1000),
        }
