from __future__ import annotations

from enum import Enum

class OperationalState(str, Enum):
    OFFENSE = "OFFENSE"
    CAUTION = "CAUTION"
    OBSERVE = "OBSERVE"
    DEFENSE = "DEFENSE"

class DecisionLabel(str, Enum):
    ENTRY_STRONG = "ENTRADA_FORTE"
    ENTRY_CAUTION = "ENTRADA_CAUTELA"
    OBSERVE = "OBSERVAR"
    NO_TRADE = "NAO_OPERAR"

class ExecutionPermission(str, Enum):
    RELEASED = "LIBERADO"
    CAUTION_OPERABLE = "CAUTELA_OPERAVEL"
    BLOCKED = "BLOQUEADO"
