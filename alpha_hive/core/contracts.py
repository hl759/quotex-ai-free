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
    display_asset: Optional[str] = None
    source_symbol: Optional[str] = None
    source_kind: str = "standard"

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

    regime_transition_state: str = "stable"
    trend_persistence: float = 0.0
    exhaustion_risk: float = 0.0
    fake_move_risk: float = 0.0
    compression_state: str = "normal"
    followthrough_bias: float = 0.0
    provider_confidence: float = 1.0
    source_kind: str = "standard"
    source_symbol: str = ""

    # ── ATR (Average True Range) ──────────────────────────────────────────
    atr: float = 0.0
    atr_pct: float = 0.0  # ATR as % of price

    # ── Enhanced Price Action Patterns ────────────────────────────────────
    price_action_pattern: str = "none"  # pin_bar, engulfing, marubozu, inside_bar, doji, none
    pattern_strength: float = 0.0       # 0.0–1.0

    # ── Swing Structure ───────────────────────────────────────────────────
    swing_high_recent: float = 0.0      # most recent swing high price
    swing_low_recent: float = 0.0       # most recent swing low price
    near_swing_high: bool = False       # price within ATR*0.5 of swing high
    near_swing_low: bool = False        # price within ATR*0.5 of swing low
    structure_break: bool = False       # price closed beyond a swing point
    structure_break_direction: str = "none"  # "bullish" | "bearish" | "none"

    # ── Smart Money Concepts (ICT/SMC) ────────────────────────────────────
    order_block_bullish: bool = False   # price at active bullish order block
    order_block_bearish: bool = False   # price at active bearish order block
    order_block_level: float = 0.0     # price level of the order block
    fvg_bullish: bool = False           # recent unfilled bullish fair value gap
    fvg_bearish: bool = False           # recent unfilled bearish fair value gap
    fvg_size_pct: float = 0.0          # FVG size as % of price
    mss_detected: bool = False          # market structure shift detected
    mss_direction: str = "none"         # "bullish" | "bearish" | "none"
    liquidity_grab: bool = False        # stop hunt / liquidity sweep detected
    liquidity_grab_direction: str = "none"  # "bullish" | "bearish" | "none"
    displacement: bool = False          # strong institutional displacement candle
    displacement_direction: str = "none"    # "bullish" | "bearish" | "none"

    # ── Trend Strength ────────────────────────────────────────────────────
    trend_strength: float = 0.0         # price efficiency ratio 0–1 (ADX proxy)

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
    meta_rank_score: float = 0.0
    meta_state: str = "neutral"
    meta_reasons: List[str] = field(default_factory=list)

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
    signal_analysis_ts: Optional[float] = None
    signal_entry_ts: Optional[float] = None
    signal_expiration_ts: Optional[float] = None
    entry_candle_ts: Optional[float] = None
    exit_candle_ts: Optional[float] = None
    evaluated_at_ts: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
