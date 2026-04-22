from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist


class StructureSpecialist(BaseSpecialist):
    """
    Especialista em estrutura de mercado:
    - Structure Breaks (quebra de swing high/low)
    - Proximidade a níveis de swing (suporte/resistência)
    - Confluência com rejeição e tendência

    Só vota quando há sinal estrutural claro — não duplica análise de outros especialistas.
    """

    name = "structure"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        strength = 0.0
        direction: str | None = None
        reasons: list[str] = []

        # ── 1. Structure Break: fechamento além de um swing point ─────────
        if features.structure_break:
            sb_dir = features.structure_break_direction
            if sb_dir == "bullish":
                direction = "CALL"
                strength += 0.78
                reasons.append("Structure break bullish: fechamento acima de swing high")
            elif sb_dir == "bearish":
                direction = "PUT"
                strength += 0.78
                reasons.append("Structure break bearish: fechamento abaixo de swing low")

        # ── 2. Proximidade a swing sem quebra (zona de S/R) ───────────────
        if not features.structure_break:
            if features.near_swing_low:
                # Perto de suporte
                if features.trend_m1 == "bull":
                    direction = "CALL"
                    strength += 0.58
                    reasons.append("Preço em zona de swing low (suporte) em tendência bullish")
                elif features.trend_m1 == "bear":
                    # Tendência bearish + suporte → pode romper para baixo
                    direction = "PUT"
                    strength += 0.38
                    reasons.append("Preço em swing low com tendência bearish (possível rompimento)")

            if features.near_swing_high:
                # Perto de resistência
                if features.trend_m1 == "bear":
                    direction = "PUT"
                    strength += 0.58
                    reasons.append("Preço em zona de swing high (resistência) em tendência bearish")
                elif features.trend_m1 == "bull":
                    # Tendência bullish + resistência → pode romper para cima
                    direction = "CALL"
                    strength += 0.38
                    reasons.append("Preço em swing high com tendência bullish (possível rompimento)")

        # Sem sinal estrutural → sem voto
        if direction is None or strength <= 0.0:
            return SpecialistVote(
                self.name, None, 0.0, 50, "fragil", 0.0, False,
                ["Sem sinal estrutural relevante neste momento"]
            )

        # ── Ajustes de qualidade ──────────────────────────────────────────

        # Bônus: rejeição forte no nível estrutural
        if features.rejection_quality == "strong":
            strength = min(1.6, strength + 0.28)
            reasons.append("Rejeição forte confirma nível estrutural")
        elif features.rejection_quality == "weak" and features.rejection:
            strength = min(1.6, strength + 0.12)
            reasons.append("Rejeição fraca no nível")

        # Bônus: alinhamento M1 + M5
        if direction == "CALL" and features.trend_m5 == "bull" and features.trend_m1 == "bull":
            strength = min(1.6, strength + 0.16)
            reasons.append("Estrutura alinhada com tendência M1+M5 bullish")
        elif direction == "PUT" and features.trend_m5 == "bear" and features.trend_m1 == "bear":
            strength = min(1.6, strength + 0.16)
            reasons.append("Estrutura alinhada com tendência M1+M5 bearish")

        # Bônus: qualidade de tendência forte
        if features.trend_quality_signal == "forte":
            strength = min(1.6, strength + 0.10)
            reasons.append("Qualidade estrutural de tendência forte")

        # Bônus: structure break + FVG na mesma direção (SMC confluência)
        if features.structure_break:
            if direction == "CALL" and features.fvg_bullish:
                strength = min(1.6, strength + 0.15)
                reasons.append("FVG bullish reforça structure break")
            elif direction == "PUT" and features.fvg_bearish:
                strength = min(1.6, strength + 0.15)
                reasons.append("FVG bearish reforça structure break")

        # Penalidade: entrada tardia
        if features.late_entry_risk or features.moved_too_fast:
            strength = max(0.0, strength - 0.24)
            reasons.append("Penalidade: movimento já correu antes da entrada")

        # Penalidade: regime caótico
        if features.regime == "chaotic":
            strength = max(0.0, strength * 0.25)
            reasons.append("Penalidade severa: regime caótico invalida análise estrutural")

        strength = round(max(0.0, strength), 2)
        confidence = int(max(50, min(90, 50 + strength * 26)))

        if strength >= 1.0:
            setup_quality = "premium"
        elif strength >= 0.65:
            setup_quality = "favoravel"
        elif strength >= 0.40:
            setup_quality = "monitorado"
        else:
            setup_quality = "fragil"

        market_fit = round(min(1.0, strength / 1.5), 2)

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
