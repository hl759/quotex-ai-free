from __future__ import annotations

from alpha_hive.core.enums import ExecutionPermission

def resolve_execution_permission(decision_cap: str | None, hard_block: bool, stake_multiplier: float) -> str:
    if hard_block or decision_cap == "NAO_OPERAR":
        return ExecutionPermission.BLOCKED.value
    if decision_cap in ("OBSERVAR", "ENTRADA_CAUTELA") or stake_multiplier < 0.95:
        return ExecutionPermission.CAUTION_OPERABLE.value
    return ExecutionPermission.RELEASED.value
