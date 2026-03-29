import math

from config import (
    ALPHA_HIVE_MODE,
    EDGE_GUARD_ACTIVE,
    EDGE_LIVE_MIN_PROB,
    EDGE_MIN_PROFIT_FACTOR,
    EDGE_PROOF_MIN_TRADES,
    EDGE_RECENT_KILL_EXPECTANCY_R,
    EDGE_RECENT_KILL_WINDOW,
    EDGE_RECENT_WARN_EXPECTANCY_R,
    EDGE_RECENT_WINDOW,
    EDGE_SEGMENT_MIN_PROFIT_FACTOR,
    EDGE_SEGMENT_MIN_TRADES,
    EDGE_VALIDATION_MIN_PROB,
)
from edge_audit import EdgeAuditEngine


class EdgeGuardEngine:
    def __init__(self):
        self.audit = EdgeAuditEngine()
        self.mode = str(ALPHA_HIVE_MODE or "validation").strip().lower()
        self.active = bool(EDGE_GUARD_ACTIVE)

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _hour_bucket(self, analysis_time):
        try:
            text = str(analysis_time or "").strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def _cap_rank(self, decision):
        order = {"NAO_OPERAR": 0, "OBSERVAR": 1, "ENTRADA_CAUTELA": 2, "ENTRADA_FORTE": 3}
        return order.get(str(decision), 0)

    def _merge_cap(self, current_cap, new_cap):
        if not current_cap:
            return new_cap
        return current_cap if self._cap_rank(current_cap) <= self._cap_rank(new_cap) else new_cap

    def _find_segment(self, rows, key, value):
        value = str(value or "unknown")
        for row in rows or []:
            if str(row.get(key, "unknown")) == value:
                return row
        return None

    def _segment_good(self, row):
        if not row:
            return None
        total = int(row.get("total", 0) or 0)
        if total < EDGE_SEGMENT_MIN_TRADES:
            return None
        expectancy = self._safe_float(row.get("expectancy_r"), 0.0)
        pf = self._safe_float(row.get("profit_factor"), 0.0)
        wr = self._safe_float(row.get("winrate"), 0.0)
        be = self._safe_float(row.get("breakeven_winrate"), 100.0)
        prob = self._safe_float(row.get("posterior_prob_edge"), 0.0)
        return expectancy > 0 and pf >= EDGE_SEGMENT_MIN_PROFIT_FACTOR and wr > be and prob >= 0.52

    def evaluate(self, asset, regime, strategy_name, analysis_time, proposed_decision, proposed_score, proposed_confidence):
        if not self.active:
            return {
                "active": False,
                "mode": self.mode,
                "decision_cap": None,
                "stake_multiplier": 1.0,
                "live_allowed": True,
                "reasons": ["Edge Guard desativado"],
                "report": {},
            }

        report = self.audit.compute_report()
        reasons = []
        decision_cap = None
        stake_multiplier = 1.0
        live_allowed = True

        summary = report.get("summary", {})
        recent_short = report.get(f"recent_{EDGE_RECENT_WINDOW}", report.get("recent_20", {}))
        recent_kill = report.get(f"recent_{EDGE_RECENT_KILL_WINDOW}", None)
        if not recent_kill:
            ledger = self.audit.load_ledger()
            valid = [t for t in ledger if str(t.get("result", "")).upper() in ("WIN", "LOSS")][:EDGE_RECENT_KILL_WINDOW]
            recent_kill = self.audit._summary(valid)

        global_total = int(summary.get("total", 0) or 0)
        global_expectancy = self._safe_float(summary.get("expectancy_r"), 0.0)
        global_pf = self._safe_float(summary.get("profit_factor"), 0.0)
        global_wr = self._safe_float(summary.get("winrate"), 0.0)
        global_be = self._safe_float(summary.get("breakeven_winrate"), 100.0)
        global_prob = self._safe_float(summary.get("posterior_prob_edge"), 0.0)

        if self.mode == "shadow":
            decision_cap = "OBSERVAR"
            stake_multiplier = 0.0
            live_allowed = False
            reasons.append("Modo shadow: sinais apenas para auditoria")

        kill_total = int(recent_kill.get("total", 0) or 0)
        kill_exp = self._safe_float(recent_kill.get("expectancy_r"), 0.0)
        kill_pf = self._safe_float(recent_kill.get("profit_factor"), 0.0)
        kill_prob = self._safe_float(recent_kill.get("posterior_prob_edge"), 0.0)
        if kill_total >= max(8, EDGE_RECENT_KILL_WINDOW):
            if kill_exp <= EDGE_RECENT_KILL_EXPECTANCY_R or kill_pf < 0.90 or kill_prob < 0.40:
                decision_cap = self._merge_cap(decision_cap, "OBSERVAR" if self.mode == "validation" else "NAO_OPERAR")
                stake_multiplier = min(stake_multiplier, 0.0 if self.mode == "live" else 0.15)
                live_allowed = False if self.mode == "live" else live_allowed
                reasons.append("Kill-switch recente: drift negativo detectado")

        recent_total = int(recent_short.get("total", 0) or 0)
        recent_exp = self._safe_float(recent_short.get("expectancy_r"), 0.0)
        recent_pf = self._safe_float(recent_short.get("profit_factor"), 0.0)
        recent_prob = self._safe_float(recent_short.get("posterior_prob_edge"), 0.0)
        if recent_total >= max(12, EDGE_RECENT_WINDOW // 2):
            if recent_exp <= EDGE_RECENT_WARN_EXPECTANCY_R or recent_pf < 1.0 or recent_prob < 0.50:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.45)
                reasons.append("Janela recente fraca: reduzindo agressividade")

        if global_total < max(30, EDGE_SEGMENT_MIN_TRADES):
            decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
            stake_multiplier = min(stake_multiplier, 0.20)
            live_allowed = False
            reasons.append("Amostra global insuficiente: operar só como observação")
        elif global_total < EDGE_PROOF_MIN_TRADES:
            if global_expectancy > 0 and global_pf >= 1.0 and global_prob >= 0.55:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.40)
                reasons.append("Edge ainda em validação: cautela e stake reduzida")
            else:
                decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
                stake_multiplier = min(stake_multiplier, 0.20)
                live_allowed = False
                reasons.append("Global ainda não positivo o bastante para validar")
        else:
            required_prob = EDGE_LIVE_MIN_PROB if self.mode == "live" else EDGE_VALIDATION_MIN_PROB
            if not (global_expectancy > 0 and global_pf >= EDGE_MIN_PROFIT_FACTOR and global_wr > global_be and global_prob >= required_prob):
                decision_cap = self._merge_cap(decision_cap, "OBSERVAR" if self.mode == "validation" else "NAO_OPERAR")
                stake_multiplier = min(stake_multiplier, 0.20 if self.mode == "validation" else 0.0)
                live_allowed = False if self.mode == "live" else live_allowed
                reasons.append("Edge global não está provado o bastante para modo atual")
            else:
                reasons.append("Edge global passou no gate principal")

        asset_row = self._find_segment(report.get("top_assets", []) + report.get("weak_assets", []), "asset", asset)
        regime_row = self._find_segment(report.get("top_regimes", []), "regime", regime)
        strategy_row = self._find_segment(report.get("top_strategies", []), "strategy_name", strategy_name)
        hour_row = self._find_segment(report.get("top_hours", []), "hour", self._hour_bucket(analysis_time))

        segment_checks = [
            ("ativo", asset_row),
            ("regime", regime_row),
            ("estratégia", strategy_row),
            ("horário", hour_row),
        ]
        unknown_segments = 0
        weak_segments = 0
        strong_segments = 0
        for label, row in segment_checks:
            good = self._segment_good(row)
            if good is None:
                unknown_segments += 1
                stake_multiplier = min(stake_multiplier, 0.75)
                reasons.append(f"Segmento sem prova suficiente: {label}")
            elif good:
                strong_segments += 1
                reasons.append(f"Segmento favorece execução: {label}")
            else:
                weak_segments += 1
                stake_multiplier = min(stake_multiplier, 0.45)
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                reasons.append(f"Segmento fraco: {label}")

        if weak_segments >= 2:
            decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
            stake_multiplier = min(stake_multiplier, 0.20)
            reasons.append("Múltiplos segmentos fracos: entrada vira observação")

        if strong_segments >= 3 and global_total >= EDGE_PROOF_MIN_TRADES and global_expectancy > 0 and recent_exp > 0:
            stake_multiplier = min(1.0, max(stake_multiplier, 0.90))
            reasons.append("Confluência estatística forte: mantendo stake alta")

        if proposed_decision == "ENTRADA_FORTE" and self.mode != "live" and global_total < EDGE_PROOF_MIN_TRADES:
            decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
            reasons.append("Sem prova completa, ENTRADA_FORTE é rebaixada")

        return {
            "active": True,
            "mode": self.mode,
            "decision_cap": decision_cap,
            "stake_multiplier": round(max(0.0, min(1.0, stake_multiplier)), 2),
            "live_allowed": bool(live_allowed and (decision_cap != "NAO_OPERAR")),
            "reasons": reasons,
            "report": {
                "summary": summary,
                "recent": recent_short,
                "asset": asset_row,
                "regime": regime_row,
                "strategy": strategy_row,
                "hour": hour_row,
            },
        }
