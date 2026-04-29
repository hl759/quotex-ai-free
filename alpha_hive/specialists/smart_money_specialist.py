from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist


class SmartMoneySpecialist(BaseSpecialist):
    """
    Especialista em Smart Money Concepts (ICT):
    - Liquidity Grabs (sweeps de swing + reversão)
    - Market Structure Shifts (MSS)
    - Order Blocks (zonas de demanda/oferta institucional)
    - Fair Value Gaps (imbalâncias)
    - Displacement (candle institucional forte)

    Prioridade de sinal: LiqGrab > MSS > OB > FVG > Displacement
    Só vota quando há sinal SMC claro — nunca infere do trend_m1.
    """

    name = "smart_money"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction: str | None = None
        reasons: list[str] = []

        # ── 1. Liquidity Grab (maior convicção: stop hunt + reversão) ─────
        if features.liquidity_grab:
            liq_dir = features.liquidity_grab_direction
            if liq_dir == "bullish":
                direction = "CALL"
                strength += 0.88
                reasons.append("Liquidity grab bullish: sweep abaixo de swing low com reversão")
            elif liq_dir == "bearish":
                direction = "PUT"
                strength += 0.88
                reasons.append("Liquidity grab bearish: sweep acima de swing high com reversão")

        # ── 2. Market Structure Shift ─────────────────────────────────────
        if features.mss_detected:
            mss_dir = features.mss_direction
            if mss_dir == "bullish":
                if direction is None:
                    direction = "CALL"
                    strength += 0.72
                    reasons.append("MSS bullish: quebra de swing high contra tendência bearish")
                elif direction == "CALL":
                    strength += 0.30
                    reasons.append("MSS bullish confirma direção CALL")
                else:
                    # MSS contradiz o liquidity grab
                    strength = max(0.0, strength - 0.35)
                    reasons.append("MSS bullish contradiz sinal bearish anterior")
            elif mss_dir == "bearish":
                if direction is None:
                    direction = "PUT"
                    strength += 0.72
                    reasons.append("MSS bearish: quebra de swing low contra tendência bullish")
                elif direction == "PUT":
                    strength += 0.30
                    reasons.append("MSS bearish confirma direção PUT")
                else:
                    strength = max(0.0, strength - 0.35)
                    reasons.append("MSS bearish contradiz sinal bullish anterior")

        # ── 3. Order Block ────────────────────────────────────────────────
        if features.order_block_bullish:
            if direction is None:
                direction = "CALL"
                strength += 0.65
                reasons.append("Preço em Order Block bullish (zona de demanda institucional)")
            elif direction == "CALL":
                strength += 0.22
                reasons.append("OB bullish reforça confluência CALL")
            else:
                strength = max(0.0, strength - 0.18)
                reasons.append("OB bullish contradiz direção PUT")

        if features.order_block_bearish:
            if direction is None:
                direction = "PUT"
                strength += 0.65
                reasons.append("Preço em Order Block bearish (zona de oferta institucional)")
            elif direction == "PUT":
                strength += 0.22
                reasons.append("OB bearish reforça confluência PUT")
            else:
                strength = max(0.0, strength - 0.18)
                reasons.append("OB bearish contradiz direção CALL")

        # ── 4. Fair Value Gap ─────────────────────────────────────────────
        if features.fvg_bullish:
            if direction is None:
                direction = "CALL"
                strength += 0.48
                reasons.append(f"FVG bullish presente (imbalância {features.fvg_size_pct:.4f})")
            elif direction == "CALL":
                strength += 0.18
                reasons.append("FVG bullish reforça confluência CALL")

        if features.fvg_bearish:
            if direction is None:
                direction = "PUT"
                strength += 0.48
                reasons.append(f"FVG bearish presente (imbalância {features.fvg_size_pct:.4f})")
            elif direction == "PUT":
                strength += 0.18
                reasons.append("FVG bearish reforça confluência PUT")

        # ── 5. Displacement ───────────────────────────────────────────────
        if features.displacement:
            disp_dir = features.displacement_direction
            if disp_dir == "bullish" and direction == "CALL":
                strength += 0.28
                reasons.append("Displacement bullish confirma impulso institucional")
            elif disp_dir == "bearish" and direction == "PUT":
                strength += 0.28
                reasons.append("Displacement bearish confirma impulso institucional")
            elif disp_dir == "bullish" and direction == "PUT":
                strength = max(0.0, strength - 0.22)
                reasons.append("Displacement bullish contradiz direção PUT")
            elif disp_dir == "bearish" and direction == "CALL":
                strength = max(0.0, strength - 0.22)
                reasons.append("Displacement bearish contradiz direção CALL")

        # Sem sinal SMC → sem voto
        if direction is None or strength <= 0.0:
            return SpecialistVote(
                self.name, None, 0.0, 50, "fragil", 0.0, False,
                ["Sem confluência SMC/ICT identificada neste momento"]
            )

        # ── Ajustes de qualidade ──────────────────────────────────────────

        # Bônus: alinhamento com tendência M5 (contexto macro)
        if direction == "CALL" and features.trend_m5 == "bull":
            strength = min(1.8, strength + 0.16)
            reasons.append("SMC alinhado com bias M5 bullish")
        elif direction == "PUT" and features.trend_m5 == "bear":
            strength = min(1.8, strength + 0.16)
            reasons.append("SMC alinhado com bias M5 bearish")

        # Bônus: rejeição confirma zona SMC
        if features.rejection_quality == "strong":
            strength = min(1.8, strength + 0.14)
            reasons.append("Rejeição forte confirma zona SMC")

        # Penalidade: entrada tardia / exaustão
        if features.late_entry_risk or features.explosive_expansion:
            strength = max(0.0, strength - 0.28)
            reasons.append("Penalidade: movimento já exausto — timing comprometido")

        # Penalidade: regime caótico
        if features.regime == "chaotic":
            strength = max(0.0, strength * 0.30)
            reasons.append("Penalidade severa: regime caótico invalida sinal SMC")

        strength = round(max(0.0, strength), 2)
        confidence = int(max(50, min(94, 50 + strength * 26)))

        if strength >= 1.2:
            setup_quality = "premium"
        elif strength >= 0.80:
            setup_quality = "favoravel"
        elif strength >= 0.48:
            setup_quality = "monitorado"
        else:
            setup_quality = "fragil"

        market_fit = round(min(1.0, strength / 1.8), 2)

        return SpecialistVote(
            self.name,
            direction,
            strength,
            confidence,
            setup_quality,
            market_fit,
            False,
            reasons,
        )
