from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from alpha_hive.config import SETTINGS
from alpha_hive.core.clock import now_brazil
from alpha_hive.services import scan_service as scan_module

log = logging.getLogger(__name__)


def _direction(d: Dict[str, Any]) -> Optional[str]:
    return d.get("direction") or d.get("signal")


def _features(d: Dict[str, Any]) -> Dict[str, Any]:
    return dict(d.get("features") or {})


def _planned_window(analysis_ts: Optional[float] = None, timeframe: str = "M1") -> Dict[str, Any]:
    analysis_ts = float(analysis_ts or time.time())
    tf = str(timeframe or "M1").upper()
    minutes = 5 if tf == "M5" else 1
    min_lead = max(20, int(getattr(SETTINGS, "signal_min_lead_seconds", 25) or 25))

    next_minute = int(((analysis_ts + 59) // 60) * 60)
    if next_minute - analysis_ts >= min_lead:
        entry_ts = next_minute
        offset = 1
    else:
        entry_ts = next_minute + 60
        offset = 2

    expiration_ts = entry_ts + (minutes * 60)
    tz = now_brazil().tzinfo
    entry_dt = datetime.fromtimestamp(entry_ts, tz=tz)
    expiration_dt = datetime.fromtimestamp(expiration_ts, tz=tz)
    lead = max(0, int(entry_ts - analysis_ts))
    now_local = now_brazil()
    return {
        "analysis_ts": analysis_ts,
        "analysis_time": now_local.strftime("%H:%M"),
        "analysis_time_exact": now_local.strftime("%H:%M:%S"),
        "entry_ts": entry_ts,
        "entry_time": entry_dt.strftime("%H:%M"),
        "expiration_ts": expiration_ts,
        "expiration": expiration_dt.strftime("%H:%M"),
        "lead_seconds": lead,
        "timeframe": tf,
        "timeframe_label": tf,
        "timeframe_minutes": minutes,
        "expiration_minutes": minutes,
        "entry_offset_minutes": offset,
        "operable_window": offset in (1, 2) and min_lead <= lead <= 120,
    }


def _block_reason(d: Optional[Dict[str, Any]], plan: Dict[str, Any], timeframe: str) -> str:
    if not isinstance(d, dict) or not d:
        return "sem decisão válida"
    if _direction(d) not in ("CALL", "PUT"):
        return "sem direção CALL/PUT"
    if d.get("execution_permission") not in ("LIBERADO", "CAUTELA_OPERAVEL"):
        return "governança bloqueou a execução"
    if d.get("decision") not in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
        return "decisão não é entrada operável"
    if not plan.get("operable_window"):
        return "janela de entrada fora do próximo minuto ou segundo próximo minuto"

    f = _features(d)
    dq = f.get("data_quality_score", d.get("data_quality_score"))
    try:
        if dq is not None and float(dq) < float(getattr(SETTINGS, "data_quality_min_operable", 0.60)):
            return "qualidade de dados insuficiente"
    except Exception:
        pass

    if bool(f.get("late_entry_risk", False)) or bool(f.get("moved_too_fast", False)):
        return "entrada tardia ou movimento já esticado"
    if bool(f.get("overextended_move", False)):
        return "movimento sobre-estendido"

    tf = str(timeframe or "M1").upper()
    if tf == "M5":
        trend_m1 = str(f.get("trend_m1", "unknown"))
        trend_m5 = str(f.get("trend_m5", "unknown"))
        if trend_m1 != "unknown" and trend_m5 != "unknown" and trend_m1 != trend_m5:
            return "M5 bloqueado por conflito entre M1 e M5"
        regime = str(f.get("regime", d.get("state", ""))).lower()
        if any(x in regime for x in ("chaos", "chop", "transition", "instavel", "unstable")):
            return "M5 bloqueado por regime instável"
        if int(d.get("confidence", 0) or 0) < 78:
            return "M5 exige confiança mínima de 78%"
        consensus = str(d.get("consensus_quality", "")).lower()
        if consensus not in ("measured", "prime", "strong", "aligned", "clean", "forte"):
            return "M5 exige consenso medido ou prime"
    return ""


def _make_signal(d: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    tf = str(plan.get("timeframe", "M1")).upper()
    out = dict(d)
    out.update({
        "signal": _direction(d),
        "direction": _direction(d),
        "analysis_time": plan["analysis_time"],
        "analysis_time_exact": plan["analysis_time_exact"],
        "analysis_ts": plan["analysis_ts"],
        "entry_time": plan["entry_time"],
        "entry_ts": plan["entry_ts"],
        "expiration": plan["expiration"],
        "expiration_ts": plan["expiration_ts"],
        "lead_seconds": plan["lead_seconds"],
        "timeframe": tf,
        "timeframe_label": tf,
        "timeframe_minutes": plan.get("timeframe_minutes", 1),
        "expiration_minutes": plan.get("expiration_minutes", 1),
        "entry_offset_minutes": plan.get("entry_offset_minutes", 1),
        "confidence_label": "ALTA" if int(d.get("confidence", 0) or 0) >= 80 else "BOA",
    })
    reasons = list(out.get("reasons") or [])
    reasons.extend([
        f"{tf}: entrada no {int(plan.get('entry_offset_minutes', 1))}º próximo minuto",
        f"Expiração {tf}: {int(plan.get('expiration_minutes', 1))} minuto(s)",
    ])
    out["reasons"] = reasons[:12]
    return out


def _schedule_row(service, signal: Dict[str, Any]) -> None:
    try:
        tf = str(signal.get("timeframe", "M1")).upper()
        slot = datetime.fromtimestamp(float(signal.get("entry_ts", 0)), tz=now_brazil().tzinfo).strftime("%Y%m%d%H%M")
        uid = "-".join([
            slot,
            tf,
            str(signal.get("asset", "NA")),
            str(signal.get("direction", signal.get("signal", "NA"))),
            str(signal.get("decision", "ENTRADA")),
        ])
        payload = dict(signal)
        payload.update({
            "uid": uid,
            "status": "pending",
            "created_at_ts": signal.get("analysis_ts"),
            "expires_at_ts": signal.get("expiration_ts"),
            "shadow_only": False,
        })
        service.store.upsert_collection_item(scan_module.PENDING_COLLECTION, uid, payload)
    except Exception as exc:
        log.warning("M1/M5 patch: falha ao agendar pendência (%s)", exc)


def install_m1_m5_operability_patch() -> None:
    cls = scan_module.ScanService
    if getattr(cls, "_m1_m5_operability_patch", False):
        return

    original_run_once = cls.run_once
    cls._m1_m5_operability_patch = True
    cls._original_run_once = original_run_once

    def patched_run_once(self, trigger: str = "manual") -> Dict[str, object]:
        result = original_run_once(self, trigger)
        try:
            current = self.runtime.get("current_decision", {})
            if not isinstance(current, dict) or not current:
                return result

            analysis_ts = float(current.get("analysis_ts", 0) or time.time())
            plan_m1 = _planned_window(analysis_ts=analysis_ts, timeframe="M1")
            plan_m5 = _planned_window(analysis_ts=analysis_ts, timeframe="M5")

            signals: List[Dict[str, Any]] = []
            m1_block = _block_reason(current, plan_m1, "M1")
            m5_block = _block_reason(current, plan_m5, "M5")

            if not m1_block:
                sig_m1 = _make_signal(current, plan_m1)
                signals.append(sig_m1)
                _schedule_row(self, sig_m1)
            if not m5_block:
                sig_m5 = _make_signal(current, plan_m5)
                signals.append(sig_m5)
                _schedule_row(self, sig_m5)

            if signals:
                self.runtime["signals"] = signals
                display = signals[0]
                self.runtime["current_decision"] = {**current, **display, "operability_block_reason": ""}
                meta = self._meta()
                meta["signal_count"] = len(signals)
                meta["m1_signal_emitted"] = any(s.get("timeframe") == "M1" for s in signals)
                meta["m5_signal_emitted"] = any(s.get("timeframe") == "M5" for s in signals)
            else:
                current["operability_block_reason"] = m1_block or m5_block or "sem janela operável"
                self.runtime["current_decision"] = current
                self.runtime["signals"] = []
                self._meta()["signal_count"] = 0

            self._persist_runtime()
            if isinstance(result, dict):
                result["signals"] = self.runtime.get("signals", [])
                result["current_decision"] = self.runtime.get("current_decision", {})
            return result
        except Exception as exc:
            log.warning("M1/M5 patch: falha no pós-processamento (%s)", exc)
            return result

    cls.run_once = patched_run_once
