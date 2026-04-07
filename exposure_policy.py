from __future__ import annotations

from alpha_hive.core.enums import DecisionLabel, OperationalState

def state_from_decision(decision: str) -> str:
    if decision == DecisionLabel.ENTRY_STRONG.value:
        return OperationalState.OFFENSE.value
    if decision == DecisionLabel.ENTRY_CAUTION.value:
        return OperationalState.CAUTION.value
    if decision == DecisionLabel.OBSERVE.value:
        return OperationalState.OBSERVE.value
    return OperationalState.DEFENSE.value
