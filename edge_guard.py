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
    EDGE_EXPLORATION_STAKE_MULTIPLIER,
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

    def _bootstrap_ready(self, proposed_decision, proposed_score, proposed_confidence, kill_locked=False):
        if not BOOTSTRAP_ACTIVE or kill_locked:
            return False
        if str(proposed_decision) not in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
            return False
        confidence = self._safe_float(proposed_confidence, 0.0)
        score = self._safe_float(proposed_score, 0.0)
        return confidence >= BOOTSTRAP_MIN_CONFIDENCE and score >= BOOTSTRAP_MIN_SCORE

    def _operable_setup(self, proposed_decision, proposed_score, proposed_confidence):
        return (
            str(proposed_decision) in ("ENTRADA_FORTE", "ENTRADA_CAUTELA")
            and self._safe_float(proposed_score, 0.0) >= 3.2
            and self._safe_float(proposed_confidence, 0.0) >= 68
        )

    def _strong_setup(self, proposed_decision, proposed_score, proposed_confidence):
        return (
            str(proposed_decision) in ("ENTRADA_FORTE", "ENTRADA_CAUTELA")
            and self._safe_float(proposed_score, 0.0) >= 4.2
            and self._safe_float(proposed_confidence, 0.0) >= 78
        )

    def _pick_dominant_reason(self, reasons):
        priorities = (
            "Kill-switch recente",
            "Janela recente",
            "Edge global",
            "Múltiplos segmentos",
            "Segmento fraco",
            "Segmento em formação",
            "Bootstrap",
            "Warmup",
            "Validação",
        )
        for prefix in priorities:
            for reason in reasons:
                if str(reason).startswith(prefix):
                    return str(reason)
        return str(reasons[0]) if reasons else "Edge Guard neutro"

    def _permission_from_state(self, decision_cap, stake_multiplier, live_allowed, hard_block=False, raw_operable=False):
        if hard_block or decision_cap == "NAO_OPERAR":
            return "BLOQUEADO"
        if decision_cap == "OBSERVAR":
            if raw_operable and stake_multiplier >= max(0.14, EDGE_EXPLORATION_STAKE_MULTIPLIER):
                return "CAUTELA_OPERAVEL"
            return "BLOQUEADO" if not live_allowed and stake_multiplier <= 0.12 else "CAUTELA_OPERAVEL"
        if decision_cap in ("ENTRADA_CAUTELA",) or stake_multiplier < 0.90 or not live_allowed:
            return "CAUTELA_OPERAVEL"
        return "LIBERADO"

    def evaluate(
        self,
        asset,
        regime,
        strategy_name,
        analysis_time,
        proposed_decision,
        proposed_score,
        proposed_confidence,
        setup_operable_raw=None,
        setup_strong_raw=None,
        structural_score_raw=None,
        structural_direction_raw=None,
        structural_quality_raw=None,
    ):
        if not self.active:
            return {
                "active": False,
                "mode": self.mode,
                "phase": "disabled",
                "bootstrap_ready": False,
                "decision_cap": None,
                "stake_multiplier": 1.0,
                "live_allowed": True,
                "hard_block": False,
                "execution_permission": "LIBERADO",
                "dominant_reason": "Edge Guard desativado",
                "reasons": ["Edge Guard desativado"],
                "report": {},
            }

        report = self.audit.compute_report()
        reasons = []
        decision_cap = None
        stake_multiplier = 1.0
        live_allowed = True
        hard_block = False

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

        raw_score = self._safe_float(structural_score_raw, proposed_score)
        raw_confidence = self._safe_float(proposed_confidence, 0.0)
        raw_operable = bool(setup_operable_raw) if setup_operable_raw is not None else self._operable_setup(proposed_decision, raw_score, raw_confidence)
        raw_strong = bool(setup_strong_raw) if setup_strong_raw is not None else self._strong_setup(proposed_decision, raw_score, raw_confidence)
        raw_direction = str(structural_direction_raw or "").upper()
        raw_quality = str(structural_quality_raw or ("favoravel" if raw_operable else "fragil")).strip().lower()
        raw_fragile = raw_quality in ("fragil", "duvidoso", "fraco")

        if self.mode == "shadow":
            decision_cap = "OBSERVAR"
            stake_multiplier = 0.0
            live_allowed = False
            reasons.append("Modo shadow: sinais apenas para auditoria")

        recent_total = int(recent_short.get("total", 0) or 0)
        recent_exp = self._safe_float(recent_short.get("expectancy_r"), 0.0)
        recent_pf = self._safe_float(recent_short.get("profit_factor"), 0.0)
        recent_prob = self._safe_float(recent_short.get("posterior_prob_edge"), 0.0)

        kill_total = int(recent_kill.get("total", 0) or 0)
        kill_exp = self._safe_float(recent_kill.get("expectancy_r"), 0.0)
        kill_pf = self._safe_float(recent_kill.get("profit_factor"), 0.0)
        kill_prob = self._safe_float(recent_kill.get("posterior_prob_edge"), 0.0)
        kill_locked = False
        if kill_total >= max(8, EDGE_RECENT_KILL_WINDOW):
            severe_kill = (kill_exp <= EDGE_RECENT_KILL_EXPECTANCY_R and kill_pf < 0.82) or kill_prob < 0.24
            moderate_kill = (kill_exp <= EDGE_RECENT_KILL_EXPECTANCY_R or kill_pf < 0.90 or kill_prob < 0.40)
            catastrophic_recent = (
                recent_total >= max(12, EDGE_RECENT_WINDOW // 2)
                and recent_exp <= (EDGE_RECENT_KILL_EXPECTANCY_R - 0.08)
                and recent_pf < 0.78
                and recent_prob < 0.24
            )
            if severe_kill:
                if raw_strong and not catastrophic_recent and raw_direction in ("CALL", "PUT"):
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, 0.22 if self.mode == "live" else 0.28)
                    reasons.append("Kill-switch recente severo: setup premium preservou cautela operável")
                elif raw_operable and not raw_fragile and not catastrophic_recent and raw_direction in ("CALL", "PUT"):
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, max(EDGE_EXPLORATION_STAKE_MULTIPLIER, 0.16))
                    reasons.append("Kill-switch recente severo: fluxo mínimo de aprendizado foi preservado")
                else:
                    decision_cap = self._merge_cap(decision_cap, "NAO_OPERAR" if self.mode == "live" else "OBSERVAR")
                    stake_multiplier = min(stake_multiplier, 0.0 if self.mode == "live" else 0.16)
                    live_allowed = False
                    kill_locked = True
                    hard_block = True
                    reasons.append("Kill-switch recente: drift negativo forte detectado")
            elif moderate_kill:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.28 if self.mode == "live" else 0.34)
                reasons.append("Kill-switch recente: drift negativo detectado, mantendo apenas cautela")

        if recent_total >= max(12, EDGE_RECENT_WINDOW // 2) and (recent_exp <= EDGE_RECENT_WARN_EXPECTANCY_R or recent_pf < 1.0 or recent_prob < 0.50):
            decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
            stake_multiplier = min(stake_multiplier, 0.80)
            reasons.append("Janela recente fraca: reduzindo agressividade")

        bootstrap_ready = self._bootstrap_ready(
            proposed_decision=proposed_decision,
            proposed_score=raw_score,
            proposed_confidence=raw_confidence,
            kill_locked=kill_locked,
        )

        if not hard_block:
            if global_total < BOOTSTRAP_MAX_TRADES:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                if bootstrap_ready:
                    stake_multiplier = min(stake_multiplier, max(BOOTSTRAP_STAKE_MULTIPLIER, 0.26))
                    reasons.append("Bootstrap inteligente: consenso forte pode operar pequeno para construir amostra")
                elif raw_operable:
                    stake_multiplier = min(stake_multiplier, max(EDGE_EXPLORATION_STAKE_MULTIPLIER, 0.18))
                    reasons.append("Bootstrap: histórico curto, mas setup bom manteve cautela operável")
                else:
                    stake_multiplier = min(stake_multiplier, max(0.14, BOOTSTRAP_STAKE_MULTIPLIER * 0.80))
                    reasons.append("Bootstrap: sem consenso forte suficiente, mas ainda operável em cautela")
            elif global_total < BOOTSTRAP_WARMUP_MAX_TRADES:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                if bootstrap_ready:
                    stake_multiplier = min(stake_multiplier, BOOTSTRAP_WARMUP_STAKE_MULTIPLIER)
                    reasons.append("Warmup: amostra curta, mas consenso forte libera cautela")
                elif global_expectancy > -0.05 and global_pf >= 0.92 and raw_operable:
                    stake_multiplier = min(stake_multiplier, 0.26)
                    reasons.append("Warmup defensivo: histórico curto, porém setup ainda operável")
                else:
                    stake_multiplier = min(stake_multiplier, 0.18)
                    reasons.append("Warmup: histórico curto e sem força suficiente para agressão, mantendo cautela")
            elif global_total < EDGE_PROOF_MIN_TRADES:
                if global_expectancy > -0.05 and global_pf >= 0.92 and global_prob >= 0.44 and raw_operable:
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, 0.72)
                    reasons.append("Edge ainda em validação: cautela operável e stake reduzida")
                elif raw_strong and recent_exp > (EDGE_RECENT_WARN_EXPECTANCY_R - 0.04):
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, 0.30)
                    reasons.append("Validação inicial: setup forte manteve fluxo mínimo de aprendizado")
                elif raw_operable:
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                    stake_multiplier = min(stake_multiplier, max(EDGE_EXPLORATION_STAKE_MULTIPLIER, 0.18))
                    reasons.append("Validação curta: contexto operável manteve cautela de baixa exposição")
                else:
                    decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
                    stake_multiplier = min(stake_multiplier, 0.18)
                    live_allowed = False
                    reasons.append("Global ainda não positivo o bastante para validar")
            else:
                required_prob = EDGE_LIVE_MIN_PROB if self.mode == "live" else EDGE_VALIDATION_MIN_PROB
                fully_proven = (global_expectancy > 0 and global_pf >= EDGE_MIN_PROFIT_FACTOR and global_wr > global_be and global_prob >= required_prob)
                near_proven = (global_expectancy > -0.04 and global_pf >= 0.95 and global_prob >= max(0.45, required_prob - 0.05))
                if not fully_proven:
                    if near_proven and raw_operable:
                        decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                        stake_multiplier = min(stake_multiplier, 0.46 if self.mode == "live" else 0.54)
                        reasons.append("Edge global quase provado: mantendo cautela tática")
                    elif raw_strong:
                        decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                        stake_multiplier = min(stake_multiplier, 0.32)
                        reasons.append("Edge global ainda incompleto, mas setup forte preservou cautela operável")
                    elif raw_operable and recent_exp > (EDGE_RECENT_KILL_EXPECTANCY_R - 0.12):
                        decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                        stake_multiplier = min(stake_multiplier, max(EDGE_EXPLORATION_STAKE_MULTIPLIER, 0.18))
                        reasons.append("Edge global fraco, porém sem colapso severo: mantendo exploração mínima")
                    else:
                        decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
                        stake_multiplier = min(stake_multiplier, 0.16 if self.mode == "live" else 0.20)
                        live_allowed = False if self.mode == "live" else live_allowed
                        reasons.append("Edge global ainda não está totalmente provado, exigindo observação")
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
        weak_segments = 0
        strong_segments = 0
        no_proof_segments = 0
        for label, row in segment_checks:
            good = self._segment_good(row)
            if good is None:
                no_proof_segments += 1
                stake_multiplier = min(stake_multiplier, 0.96)
                reasons.append(f"Segmento em formação: {label}")
            elif good:
                strong_segments += 1
                reasons.append(f"Segmento favorece execução: {label}")
            else:
                weak_segments += 1
                stake_multiplier = min(stake_multiplier, 0.74)
                if not hard_block:
                    decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                reasons.append(f"Segmento fraco: {label}")

        if weak_segments >= 3 and not hard_block:
            if raw_strong or raw_operable:
                decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
                stake_multiplier = min(stake_multiplier, 0.46 if raw_strong else 0.38)
                reasons.append("Múltiplos segmentos fracos: contexto ainda operável manteve cautela profissional")
            else:
                decision_cap = self._merge_cap(decision_cap, "OBSERVAR")
                stake_multiplier = min(stake_multiplier, 0.20)
                reasons.append("Múltiplos segmentos fracos: entrada permanece em observação")
        elif no_proof_segments >= 3 and weak_segments == 0 and raw_operable and not hard_block:
            decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
            stake_multiplier = min(stake_multiplier, max(0.18, EDGE_EXPLORATION_STAKE_MULTIPLIER))
            reasons.append("Múltiplos segmentos ainda em formação: mantendo aprendizado controlado")

        if strong_segments >= 3 and global_total >= EDGE_PROOF_MIN_TRADES and global_expectancy > 0 and recent_exp > 0:
            stake_multiplier = min(1.0, max(stake_multiplier, 0.90))
            reasons.append("Confluência estatística forte: mantendo stake alta")
        elif strong_segments >= 2 and global_total < EDGE_PROOF_MIN_TRADES and bootstrap_ready:
            stake_multiplier = min(1.0, max(stake_multiplier, BOOTSTRAP_WARMUP_STAKE_MULTIPLIER))
            reasons.append("Bootstrap com boa confluência segmentada: mantendo cautela operável")

        if proposed_decision == "ENTRADA_FORTE" and self.mode != "live" and global_total < EDGE_PROOF_MIN_TRADES and not hard_block:
            decision_cap = self._merge_cap(decision_cap, "ENTRADA_CAUTELA")
            reasons.append("Sem prova completa, ENTRADA_FORTE é rebaixada")

        if proposed_decision == "ENTRADA_CAUTELA" and global_total < EDGE_PROOF_MIN_TRADES and bootstrap_ready and recent_exp > -0.05 and not hard_block:
            stake_multiplier = min(1.0, max(stake_multiplier, 0.32))
            reasons.append("Validação equilibrada: cautela mantida com stake profissional reduzida")

        phase = "proven"
        if global_total < BOOTSTRAP_MAX_TRADES:
            phase = "bootstrap"
        elif global_total < BOOTSTRAP_WARMUP_MAX_TRADES:
            phase = "warmup"
        elif global_total < EDGE_PROOF_MIN_TRADES:
            phase = "validation"

        execution_permission = self._permission_from_state(
            decision_cap=decision_cap,
            stake_multiplier=stake_multiplier,
            live_allowed=live_allowed,
            hard_block=hard_block,
            raw_operable=raw_operable,
        )
        dominant_reason = self._pick_dominant_reason(reasons)

        return {
            "active": True,
            "mode": self.mode,
            "phase": phase,
            "bootstrap_ready": bool(bootstrap_ready),
            "decision_cap": decision_cap,
            "stake_multiplier": round(max(0.0, min(1.0, stake_multiplier)), 2),
            "live_allowed": bool(live_allowed and (decision_cap != "NAO_OPERAR") and not hard_block),
            "hard_block": bool(hard_block),
            "execution_permission": execution_permission,
            "dominant_reason": dominant_reason,
            "raw_setup_operable": raw_operable,
            "raw_setup_strong": raw_strong,
            "raw_setup_quality": raw_quality,
            "raw_direction": raw_direction,
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
