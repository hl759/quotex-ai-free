from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class MarketSnapshot:
    asset: str
    market_type: str
    provider: str
    provider_fallback_chain: List[str]
    data_quality_score: float
    data_quality_state: str
    candles_m1: List[Candle]
    candles_m5: List[Candle]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "candles_m1": [c.to_dict() for c in self.candles_m1],
            "candles_m5": [c.to_dict() for c in self.candles_m5],
        }

@dataclass
class MarketFeatures:
    asset: str
    regime: str
    trend_m1: str
    trend_m5: str
    rsi: float
    pattern: Optional[str]
    breakout: bool
    breakout_quality: str
    rejection: bool
    rejection_quality: str
    volatility: bool
    moved_too_fast: bool
    late_entry_risk: bool
    explosive_expansion: bool
    is_sideways: bool
    trend_quality_signal: str
    data_quality_score: float
    provider: str
    market_type: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class SpecialistVote:
    specialist: str
    direction: Optional[str]
    vote_strength: float
    confidence: int
    setup_quality: str
    market_fit: float
    veto: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CouncilDecision:
    consensus_direction: Optional[str]
    consensus_strength: float
    quality: str
    support_weight: float
    opposition_weight: float
    conflict_level: str
    decision_cap: Optional[str]
    top_specialists: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class RiskDecision:
    state: str
    execution_permission: str
    decision_cap: Optional[str]
    stake_multiplier: float
    hard_block: bool
    kill_switch: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class FinalDecision:
    asset: str
    state: str
    decision: str
    direction: Optional[str]
    confidence: int
    score: float
    setup_quality: str
    consensus_quality: str
    execution_permission: str
    suggested_stake: float
    risk_pct: float
    provider: str
    market_type: str
    reasons: List[str] = field(default_factory=list)
    specialist_votes: List[Dict[str, Any]] = field(default_factory=list)
    council: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class TradeOutcome:
    uid: str
    asset: str
    direction: str
    result: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    payout: float
    stake: float
    gross_pnl: float
    gross_r: float
    evaluation_mode: str
    provider: str = "unknown"
    state: str = "OBSERVE"
    consensus_strength: float = 0.0
    timing_quality: str = "unknown"
    delay_seconds: int = 0
    loss_cause: str = "none"
    reverse_would_win: bool = False
    reverse_direction: Optional[str] = None
    reverse_result: str = "DRAW"
    counterfactual_better: bool = False
    entry_efficiency: str = "normal"
    followthrough_quality: str = "normal"
    weak_followthrough: bool = False
    regime_shift_detected: bool = False
    overextension_detected: bool = False
    timing_failure_mode: str = "none"
    mae: float = 0.0
    mfe: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
