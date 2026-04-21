from __future__ import annotations

from datetime import timedelta

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.core.clock import now_brazil
from alpha_hive.services.capital_service import CapitalService


class SnapshotService:
    """
    Stateless — não mantém instâncias pesadas em RAM.
    EdgeAuditEngine e JournalManager são criados por chamada e descartados.
    CapitalService é leve (apenas lê/escreve uma chave no SQLite).
    """
    def __init__(self):
        self.capital = CapitalService()

    def _audit(self) -> EdgeAuditEngine:
        return EdgeAuditEngine()

    def _journal(self) -> JournalManager:
        return JournalManager()

    def _confidence_label(self, confidence: int) -> str:
        if confidence >= 82:
            return "FORTE"
        if confidence >= 70:
            return "MEDIO"
        return "CAUTELOSO"

    def _reason_text(self, reasons):
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

    def _times_from_item(self, item: dict, require_signal: bool = False):
        analysis_time = str(item.get("analysis_time") or "").strip()
        entry_time = str(item.get("entry_time") or "").strip()
        expiration = str(item.get("expiration") or "").strip()

        if analysis_time and entry_time and expiration and analysis_time != "--:--" and entry_time != "--:--" and expiration != "--:--":
            return analysis_time, entry_time, expiration

        direction = item.get("direction") or item.get("signal")
        execution_permission = str(item.get("execution_permission", "BLOQUEADO") or "BLOQUEADO")
        decision = str(item.get("decision", "NAO_OPERAR") or "NAO_OPERAR")
        should_plan = (
            direction in ("CALL", "PUT")
            and execution_permission != "BLOQUEADO"
            and decision in ("ENTRADA_FORTE", "ENTRADA_CAUTELA")
        )

        if require_signal or should_plan:
            raw_analysis = item.get("analysis_time") or item.get("analysis_session")
            return self._resolve_times(raw_analysis)

        return ("--:--", "--:--", "--:--")

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
            main = f"Confluencia forte {direction or 'sem direcao definida'} com execucao liberada."
        elif decision == "ENTRADA_CAUTELA":
            title = "Resumo da entrada em cautela"
            main = f"Setup operavel {direction or 'sem direcao definida'} com stake reduzida e disciplina."
        elif decision == "OBSERVAR":
            title = "Resumo da observacao"
            main = "Ha leitura de mercado, mas o contexto ainda exige observacao."
        else:
            title = "Resumo do bloqueio"
            main = "A governanca bloqueou a execucao para preservar capital e consistencia."

        points = [
            f"Regime: {regime}",
            f"Estado: {state}",
            f"Consenso: {consensus_quality}",
            f"Execucao: {execution_permission}",
            f"Setup: {setup_quality}",
        ]
        return title, main, points

    def _adapt_decision(self, item: dict) -> dict:
        if not isinstance(item, dict):
            return {}

        features = item.get("features", {}) or {}
        reasons = item.get("reasons", []) or []

        regime = item.get("regime") or features.get("regime") or "unknown"
        analysis_time, entry_time, expiration = self._times_from_item(item, require_signal=False)

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
        analysis_time, entry_time, expiration = self._times_from_item(item, require_signal=True)

        reasons = item.get("reasons", []) or []
        if not reasons:
            reasons = [
                f"Direcao dominante: {direction or 'N/A'}",
                f"Execucao: {item.get('execution_permission', 'BLOQUEADO')}",
                f"Setup: {item.get('setup_quality', 'monitorado')}",
            ]
        lead_seconds = int(item.get("lead_seconds", 0) or 0)
        if lead_seconds > 0:
            reasons = [f"Janela de entrada em {lead_seconds}s", *reasons]

        summary_title = "Resumo operacional"
        summary_main = f"Leitura {direction or 'N/A'} com confianca {confidence}%."
        summary_points = [
            f"Setup: {item.get('setup_quality', 'monitorado')}",
            f"Execucao: {item.get('execution_permission', 'BLOQUEADO')}",
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

    def _coalesce_learning_stats(self, report: dict) -> dict:
        summary = dict(report.get("summary", {}) or {})
        journal_stats = dict(self._journal().stats() or {})

        audit_total = int(summary.get("total", 0) or 0)
        audit_wins = int(summary.get("wins", 0) or 0)
        audit_loss = int(summary.get("losses", 0) or 0)

        journal_total = int(journal_stats.get("total", 0) or 0)
        journal_wins = int(journal_stats.get("wins", 0) or 0)
        journal_loss = int(journal_stats.get("loss", 0) or 0)

        if audit_total >= journal_total:
            total = audit_total
            wins = audit_wins
            loss = audit_loss
            source = "audit_summary"
        else:
            total = journal_total
            wins = journal_wins
            loss = journal_loss
            source = "journal"

        winrate = round((wins / total) * 100, 2) if total else 0.0

        return {
            "total": total,
            "wins": wins,
            "loss": loss,
            "winrate": winrate,
            "source": source,
            "audit_total": audit_total,
            "journal_total": journal_total,
        }

    def build(self, runtime: dict):
        report = self._audit().compute_report()
        learning_stats = self._coalesce_learning_stats(report)

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
        meta.setdefault("last_scan_error", "")
        meta.setdefault("last_snapshot_refresh_error", "")
        meta.setdefault("pending_total", 0)
        meta.setdefault("pending_expired", 0)
        meta.setdefault("pending_evaluated_last_scan", 0)
        meta["stats_source"] = learning_stats.get("source", "unknown")
        meta["audit_total"] = learning_stats.get("audit_total", 0)
        meta["journal_total"] = learning_stats.get("journal_total", 0)

        return {
            "signals": signals,
            "history": history,
            "current_decision": current,
            "meta": meta,
            "learning_stats": {
                "total": learning_stats["total"],
                "wins": learning_stats["wins"],
                "loss": learning_stats["loss"],
                "winrate": learning_stats["winrate"],
            },
            "best_assets": report.get("by_asset", []),
            "best_hours": report.get("by_hour", []),
            "capital_state": self.capital.get(),
            "specialist_leaders": report.get("by_specialist", []),
        }
