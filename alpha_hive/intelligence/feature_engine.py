from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot
from alpha_hive.market.indicators import IndicatorEngine
from alpha_hive.market.regime_transition_engine import RegimeTransitionEngine


class FeatureEngine:
    def __init__(self):
        self.indicators = IndicatorEngine()
        self.transitions = RegimeTransitionEngine()

    def extract(self, snapshot: MarketSnapshot) -> MarketFeatures:
        data = self.indicators.calculate(snapshot.candles_m1)
        transition = self.transitions.assess(snapshot.candles_m1, snapshot.candles_m5, data)
        provider_confidence = float(snapshot.data_quality_score)

        if "-cache" in str(snapshot.provider or ""):
            provider_confidence = round(max(0.40, provider_confidence - 0.08), 3)

        return MarketFeatures(
            # ── Campos base ───────────────────────────────────────────────
            asset=snapshot.asset,
            regime=str(data["regime"]),
            trend_m1=str(data["trend_m1"]),
            trend_m5=str(data["trend_m5"]),
            rsi=float(data["rsi"]),
            pattern=data["pattern"],
            breakout=bool(data["breakout"]),
            breakout_quality=str(data["breakout_quality"]),
            rejection=bool(data["rejection"]),
            rejection_quality=str(data["rejection_quality"]),
            volatility=bool(data["volatility"]),
            moved_too_fast=bool(data["moved_too_fast"]),
            late_entry_risk=bool(data["late_entry_risk"]),
            explosive_expansion=bool(data["explosive_expansion"]),
            is_sideways=bool(data["is_sideways"]),
            trend_quality_signal=str(data["trend_quality_signal"]),
            data_quality_score=float(snapshot.data_quality_score),
            provider=snapshot.provider,
            market_type=snapshot.market_type,
            # ── Transição de regime ───────────────────────────────────────
            regime_transition_state=str(transition["regime_transition_state"]),
            trend_persistence=float(transition["trend_persistence"]),
            exhaustion_risk=float(transition["exhaustion_risk"]),
            fake_move_risk=float(transition["fake_move_risk"]),
            compression_state=str(transition["compression_state"]),
            followthrough_bias=float(transition["followthrough_bias"]),
            provider_confidence=provider_confidence,
            source_kind=str(getattr(snapshot, "source_kind", "standard") or "standard"),
            source_symbol=str(getattr(snapshot, "source_symbol", "") or ""),
            # ── ATR ───────────────────────────────────────────────────────
            atr=float(data.get("atr", 0.0)),
            atr_pct=float(data.get("atr_pct", 0.0)),
            # ── Price action avançado ─────────────────────────────────────
            price_action_pattern=str(data.get("price_action_pattern", "none")),
            pattern_strength=float(data.get("pattern_strength", 0.0)),
            # ── Estrutura de swing ────────────────────────────────────────
            swing_high_recent=float(data.get("swing_high_recent", 0.0)),
            swing_low_recent=float(data.get("swing_low_recent", 0.0)),
            near_swing_high=bool(data.get("near_swing_high", False)),
            near_swing_low=bool(data.get("near_swing_low", False)),
            structure_break=bool(data.get("structure_break", False)),
            structure_break_direction=str(data.get("structure_break_direction", "none")),
            # ── Smart Money Concepts ──────────────────────────────────────
            order_block_bullish=bool(data.get("order_block_bullish", False)),
            order_block_bearish=bool(data.get("order_block_bearish", False)),
            order_block_level=float(data.get("order_block_level", 0.0)),
            fvg_bullish=bool(data.get("fvg_bullish", False)),
            fvg_bearish=bool(data.get("fvg_bearish", False)),
            fvg_size_pct=float(data.get("fvg_size_pct", 0.0)),
            mss_detected=bool(data.get("mss_detected", False)),
            mss_direction=str(data.get("mss_direction", "none")),
            liquidity_grab=bool(data.get("liquidity_grab", False)),
            liquidity_grab_direction=str(data.get("liquidity_grab_direction", "none")),
            displacement=bool(data.get("displacement", False)),
            displacement_direction=str(data.get("displacement_direction", "none")),
            # ── Força de tendência ────────────────────────────────────────
            trend_strength=float(data.get("trend_strength", 0.0)),
        )
