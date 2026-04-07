from __future__ import annotations

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import CouncilDecision, MarketFeatures, MarketSnapshot, RiskDecision
from alpha_hive.core.enums import DecisionLabel
from alpha_hive.risk.execution_permission import resolve_execution_permission
from alpha_hive.risk.kill_switch import evaluate_kill_switch

class EdgeGuard:
    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures, council: CouncilDecision, audit_summary: dict, setup_quality: str) -> RiskDecision:
        reasons = []
        hard_block = False
        decision_cap = None
        stake_multiplier = 1.0

        recent = audit_summary.get("recent_20", {})
        summary = audit_summary.get("summary", {})
        kill_switch = evaluate_kill_switch(recent)
        if kill_switch:
            reasons.append("Kill-switch recente ativado")
            hard_block = True
            decision_cap = DecisionLabel.NO_TRADE.value
            stake_multiplier = 0.0

        if snapshot.data_quality_score < SETTINGS.data_quality_min_operable:
            reasons.append("Qualidade de dado abaixo do mínimo operável")
            hard_block = True
            decision_cap = DecisionLabel.NO_TRADE.value
            stake_multiplier = 0.0
        elif snapshot.data_quality_score < SETTINGS.data_quality_min_offense:
            reasons.append("Qualidade de dado reduz agressividade")
            decision_cap = DecisionLabel.ENTRY_CAUTION.value
            stake_multiplier = min(stake_multiplier, 0.65)

        total = int(summary.get("total", 0) or 0)
        expectancy = float(summary.get("expectancy_r", 0.0) or 0.0)
        profit_factor = float(summary.get("profit_factor", 0.0) or 0.0)

        if total >= 20 and (expectancy <= -0.08 or profit_factor < 0.95):
            reasons.append("Edge global ainda fraco")
            decision_cap = DecisionLabel.OBSERVE.value if council.quality == "split" else DecisionLabel.ENTRY_CAUTION.value
            stake_multiplier = min(stake_multiplier, 0.45)

        if features.regime == "chaotic" or council.conflict_level == "high":
            reasons.append("Conflito alto ou regime destrutivo")
            hard_block = True
            decision_cap = DecisionLabel.NO_TRADE.value
            stake_multiplier = 0.0

        if council.quality == "fragile" and not hard_block:
            reasons.append("Consenso frágil")
            decision_cap = DecisionLabel.ENTRY_CAUTION.value
            stake_multiplier = min(stake_multiplier, 0.55)

        if setup_quality == "fragil" and not hard_block:
            reasons.append("Setup estrutural frágil")
            decision_cap = DecisionLabel.OBSERVE.value
            stake_multiplier = min(stake_multiplier, 0.25)

        state = "DEFENSE" if hard_block else "CAUTION" if decision_cap in (DecisionLabel.OBSERVE.value, DecisionLabel.ENTRY_CAUTION.value) else "OFFENSE"
        permission = resolve_execution_permission(decision_cap, hard_block, stake_multiplier)
        return RiskDecision(
            state=state,
            execution_permission=permission,
            decision_cap=decision_cap,
            stake_multiplier=round(max(0.0, min(1.0, stake_multiplier)), 2),
            hard_block=hard_block,
            kill_switch=kill_switch,
            reasons=reasons or ["Edge guard neutro"],
        )
