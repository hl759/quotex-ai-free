import math

from config import (
    ALPHA_HIVE_MODE,
    BOOTSTRAP_ACTIVE,
    BOOTSTRAP_MAX_TRADES,
    BOOTSTRAP_MIN_CONFIDENCE,
    BOOTSTRAP_MIN_SCORE,
    BOOTSTRAP_STAKE_MULTIPLIER,
    BOOTSTRAP_WARMUP_MAX_TRADES,
    BOOTSTRAP_WARMUP_STAKE_MULTIPLIER,
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
        self.mode = str(ALPHA_HIVE_MODE or "live").strip().lower()
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

    def _bootstrap_ready(self, proposed_decision, proposed_score, proposed_confidence, kill_locked=False):
        if not BOOTSTRAP_ACTIVE or kill_locked:
            return False
        if str(proposed_decision) not in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
            return False
        confidence = self._safe_float(proposed_confidence, 0.0)
        score = self._safe_float(proposed_score, 0.0)
        return confidence >= BOOTSTRAP_MIN_CONFIDENCE and score >= BOOTSTRAP_MIN_SCORE

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
        kill_locked = False
        if kill_total >= max(8, EDGE_RECENT_KILL_WINDOW):
            severe_kill = (
                kill_exp <= min(EDGE_RECENT_KILL_EXPECTANCY_R, -0.14)
                or kill_pf < 0.82
                or kill_prob < 0.34
            )
            if severe_kill:
                decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
                stake_multiplier = min(stake_multiplier, 0.0 if self.mode == "live" else 0.18)
                live_allowed = False if self.mode == "live" else True
                kill_locked = True
                reasons.append("Kill-switch recente: drift realmente negativo detectado")
            elif kill_exp <= EDGE_RECENT_WARN_EXPECTANCY_R or kill_pf < 0.92 or kill_prob < 0.42:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.35 if self.mode == "live" else 0.28)
                reasons.append("Kill-switch recente: risco elevado reduziu agressividade")

        recent_total = int(recent_short.get("total", 0) or 0)
        recent_exp = self._safe_float(recent_short.get("expectancy_r"), 0.0)
        recent_pf = self._safe_float(recent_short.get("profit_factor"), 0.0)
        recent_prob = self._safe_float(recent_short.get("posterior_prob_edge"), 0.0)
        if recent_total >= max(12, EDGE_RECENT_WINDOW // 2):
            if recent_exp <= EDGE_RECENT_WARN_EXPECTANCY_R or recent_pf < 1.0 or recent_prob < 0.50:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.72)
                reasons.append("Janela recente fraca: reduzindo agressividade")

        bootstrap_ready = self._bootstrap_ready(
            proposed_decision=proposed_decision,
            proposed_score=proposed_score,
            proposed_confidence=proposed_confidence,
            kill_locked=kill_locked,
        )

        if global_total < BOOTSTRAP_MAX_TRADES:
            if bootstrap_ready:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, max(0.16, BOOTSTRAP_STAKE_MULTIPLIER))
                reasons.append("Bootstrap inteligente: consenso forte pode operar pequeno para construir amostra")
            else:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, max(0.12, BOOTSTRAP_STAKE_MULTIPLIER * 0.90))
                reasons.append("Bootstrap: sem consenso forte suficiente, mantém cautela reduzida")
        elif global_total < BOOTSTRAP_WARMUP_MAX_TRADES:
            if bootstrap_ready:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, max(0.22, BOOTSTRAP_WARMUP_STAKE_MULTIPLIER))
                reasons.append("Warmup: amostra curta, mas consenso forte libera cautela")
            elif global_expectancy > -0.05 and global_pf >= 0.92:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, min(0.20, BOOTSTRAP_WARMUP_STAKE_MULTIPLIER))
                reasons.append("Warmup defensivo: histórico curto, porém ainda operável")
            else:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.14)
                reasons.append("Warmup: histórico curto e sem força suficiente para agressão, mantendo cautela mínima")
        elif global_total < EDGE_PROOF_MIN_TRADES:
            if global_expectancy > -0.06 and global_pf >= 0.92 and global_prob >= 0.46:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.68)
                reasons.append("Edge ainda em validação: cautela operável e stake reduzida")
            elif bootstrap_ready and recent_exp > EDGE_RECENT_WARN_EXPECTANCY_R:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, min(0.38, BOOTSTRAP_WARMUP_STAKE_MULTIPLIER))
                reasons.append("Validação inicial: consenso forte mantém entrada pequena enquanto prova amadurece")
            else:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.24)
                reasons.append("Global ainda não positivo o bastante para validar, mantendo cautela reduzida")
        else:
            required_prob = EDGE_LIVE_MIN_PROB if self.mode == "live" else EDGE_VALIDATION_MIN_PROB
            fully_proven = (global_expectancy > 0 and global_pf >= EDGE_MIN_PROFIT_FACTOR and global_wr > global_be and global_prob >= required_prob)
            near_proven = (global_expectancy > -0.05 and global_pf >= 0.92 and global_prob >= max(0.44, required_prob - 0.06))
            if not fully_proven:
                if near_proven and str(proposed_decision) in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, 0.42)
                    reasons.append("Edge global quase provado: validação manteve cautela tática")
                else:
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, 0.22)
                    reasons.append("Edge global ainda não está totalmente provado, reduzindo agressividade sem bloquear")
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
                stake_multiplier = min(stake_multiplier, 0.98)
                reasons.append(f"Segmento sem prova suficiente: {label}")
            elif good:
                strong_segments += 1
                reasons.append(f"Segmento favorece execução: {label}")
            else:
                weak_segments += 1
                stake_multiplier = min(stake_multiplier, 0.78)
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                reasons.append(f"Segmento fraco: {label}")

        if weak_segments >= 3:
            if self._safe_float(proposed_score, 0.0) >= 3.3 and self._safe_float(proposed_confidence, 0.0) >= 70:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.36)
                reasons.append("Múltiplos segmentos fracos: contexto ainda operável manteve cautela profissional")
            else:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.18)
                reasons.append("Múltiplos segmentos fracos: execução mantida apenas em cautela mínima")

        if strong_segments >= 3 and global_total >= EDGE_PROOF_MIN_TRADES and global_expectancy > 0 and recent_exp > 0:
            stake_multiplier = min(1.0, max(stake_multiplier, 0.90))
            reasons.append("Confluência estatística forte: mantendo stake alta")
        elif strong_segments >= 2 and global_total < EDGE_PROOF_MIN_TRADES and bootstrap_ready:
            stake_multiplier = min(1.0, max(stake_multiplier, BOOTSTRAP_WARMUP_STAKE_MULTIPLIER))
            reasons.append("Bootstrap com boa confluência segmentada: mantendo cautela operável")

        if proposed_decision == "ENTRADA_FORTE" and global_total < EDGE_PROOF_MIN_TRADES:
            decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
            reasons.append("Sem prova completa, ENTRADA_FORTE é rebaixada")

        if proposed_decision == "ENTRADA_CAUTELA" and global_total < EDGE_PROOF_MIN_TRADES and bootstrap_ready and recent_exp > -0.03:
            stake_multiplier = min(1.0, max(stake_multiplier, 0.34))
            reasons.append("Validação equilibrada: cautela mantida com stake profissional reduzida")

        phase = "proven"
        if global_total < BOOTSTRAP_MAX_TRADES:
            phase = "bootstrap"
        elif global_total < BOOTSTRAP_WARMUP_MAX_TRADES:
            phase = "warmup"
        elif global_total < EDGE_PROOF_MIN_TRADES:
            phase = "validation"

        return {
            "active": True,
            "mode": self.mode,
            "phase": phase,
            "bootstrap_ready": bool(bootstrap_ready),
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
