from __future__ import annotations

from datetime import timedelta

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.core.clock import now_brazil
from alpha_hive.services.capital_service import CapitalService


class SnapshotService:
    def __init__(self):
        self.audit = EdgeAuditEngine()
        self.journal = JournalManager()
        self.capital = CapitalService()

    def _confidence_label(self, confidence: int) -> str:
        if confidence >= 82:
            return "FORTE"
        if confidence >= 70:
            return "MÉDIO"
        return "CAUTELOSO"

    def _reason_text(self, reasons) -> str:
        if not isinstance(reasons, list):
            reasons = [str(reasons)] if reasons else []
        if not reasons:
            return "Sem detalhes"
        return "\n".join([f"• {str(r)}" for r in reasons[:12]])

    def _resolve_times(self, analysis_time: str | None = None):
        base = now_brazil().replace(second=0, microsecond=0)
        try:
            if analysis_time and ":" in str(analysis_time):
                parts = str(analysis_time).split(":")
                hour = int(parts[0])
                minute = int(parts[1])
                base = base.replace(hour=hour, minute=minute)
        except Exception:
            pass

        entry = base + timedelta(minutes=1)
        expiration = entry + timedelta(minutes=1)
        return (
            base.strftime("%H:%M"),
            entry.strftime("%H:%M"),
            expiration.strftime("%H:%M"),
        )

    def _summary_for_decision(self, item: dict):
        decision = str(item.get("decision", "NAO_OPERAR") or "NAO_OPERAR")
        direction = item.get("direction")
        setup_quality = str(item.get("setup_quality", "monitorado") or "monitorado")
        execution_permission = str(item.get("execution_permission", "BLOQUEADO") or "BLOQUEADO")
        regime = str(item.get("regime", "unknown") or "unknown")
        state = str(item.get("state", "OBSERVE") or "OBSERVE")
        consensus_quality = str(item.get("consensus_quality", "split") or "split")

        if decision == "ENTRADA_FORTE":
            title = "Resumo da entrada forte"
            main = f"Confluência forte {direction or 'sem direção definida'} com execução liberada."
        elif decision == "ENTRADA_CAUTELA":
            title = "Resumo da entrada em cautela"
            main = f"Setup operável {direction or 'sem direção definida'} com stake reduzida e disciplina."
        elif decision == "OBSERVAR":
            title = "Resumo da observação"
            main = "Há leitura de mercado, mas o contexto ainda exige observação."
        else:
            title = "Resumo do bloqueio"
            main = "A governança bloqueou a execução para preservar capital e consistência."

        points = [
            f"Regime: {regime}",
            f"Estado: {state}",
            f"Consenso: {consensus_quality}",
            f"Execução: {execution_permission}",
            f"Setup: {setup_quality}",
        ]
        return title, main, points

    def _adapt_decision(self, item: dict) -> dict:
        if not isinstance(item, dict):
            return {}

        features = item.get("features", {}) or {}
        reasons = item.get("reasons", []) or []

        regime = item.get("regime") or features.get("regime") or "unknown"
        raw_analysis = item.get("analysis_time") or item.get("analysis_session")
        analysis_time, entry_time, expiration = self._resolve_times(raw_analysis)

        title, main, points = self._summary_for_decision({**item, "regime": regime})

        out = dict(item)
        out["regime"] = regime
        out["analysis_time"] = analysis_time
        out["entry_time"] = entry_time
        out["expiration"] = expiration
        out["reason_text"] = self._reason_text(reasons)
        out["summary_title"] = title
        out["summary_main"] = main
        out["summary_points"] = points
        out["stake_suggested"] = item.get("suggested_stake", 0.0)
        out["provider"] = item.get("provider", "Alpha Hive")
        return out

    def _adapt_signal(self, item: dict) -> dict:
        if not isinstance(item, dict):
            return {}

        direction = item.get("signal") or item.get("direction")
        confidence = int(item.get("confidence", 50) or 50)
        raw_analysis = item.get("analysis_time")
        analysis_time, entry_time, expiration = self._resolve_times(raw_analysis)

        reasons = item.get("reasons", []) or []
        if not reasons:
            reasons = [
                f"Direção dominante: {direction or 'N/A'}",
                f"Execução: {item.get('execution_permission', 'BLOQUEADO')}",
                f"Setup: {item.get('setup_quality', 'monitorado')}",
            ]

        summary_title = "Resumo operacional"
        summary_main = f"Leitura {direction or 'N/A'} com confiança {confidence}%."
        summary_points = [
            f"Setup: {item.get('setup_quality', 'monitorado')}",
            f"Execução: {item.get('execution_permission', 'BLOQUEADO')}",
            f"Estado: {item.get('state', 'OBSERVE')}",
        ]

        out = dict(item)
        out["signal"] = direction
        out["analysis_time"] = analysis_time
        out["entry_time"] = entry_time
        out["expiration"] = expiration
        out["confidence_label"] = self._confidence_label(confidence)
        out["reason"] = reasons[:4]
        out["reason_text"] = self._reason_text(reasons)
        out["summary_title"] = summary_title
        out["summary_main"] = summary_main
        out["summary_points"] = summary_points
        out["regime"] = item.get("regime") or "unknown"
        return out

    def build(self, runtime: dict):
        report = self.audit.compute_report()

        current = self._adapt_decision(runtime.get("current_decision", {}) or {})
        signals = [self._adapt_signal(item) for item in (runtime.get("signals", []) or [])]
        history = [self._adapt_decision(item) for item in (runtime.get("history", []) or [])]

        meta = dict(runtime.get("meta", {}) or {})
        meta.setdefault("ui_auto_refresh_seconds", 20)
        meta.setdefault("ui_stale_after_seconds", 95)
        meta.setdefault("ui_force_scan_after_seconds", 110)
        meta.setdefault("signal_count", len(signals))
        meta.setdefault("asset_count", 0)
        meta.setdefault("last_scan", "--")
        meta.setdefault("scan_count", 0)
        meta.setdefault("last_scan_age_seconds", 0)
        meta.setdefault("scan_in_progress", False)

        return {
            "signals": signals,
            "history": history,
            "current_decision": current,
            "meta": meta,
            "learning_stats": self.journal.stats(),
            "best_assets": report.get("by_asset", []),
            "best_hours": [],
            "capital_state": self.capital.get(),
            "specialist_leaders": report.get("by_specialist", []),
        }
