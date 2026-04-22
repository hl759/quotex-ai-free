from __future__ import annotations

from alpha_hive.core.contracts import MarketFeatures, MarketSnapshot, SpecialistVote
from alpha_hive.specialists.base import BaseSpecialist

# Padrões que definem direção diretamente
_BULLISH_PATTERNS = {"bullish_pin_bar", "bullish_engulfing", "bullish_marubozu"}
_BEARISH_PATTERNS = {"bearish_pin_bar", "bearish_engulfing", "bearish_marubozu"}


class PriceActionSpecialist(BaseSpecialist):
    """
    Especialista em Price Action: avalia padrões de candle (pin bars, engolfantes,
    marubozu, inside bar, doji) e os contextualiza com estrutura e tendência.
    Só vota quando existe um padrão claro — nunca infere direção do trend_m1.
    """

    name = "price_action"

    def evaluate(self, snapshot: MarketSnapshot, features: MarketFeatures) -> SpecialistVote:
        pattern = features.price_action_pattern
        base_strength = features.pattern_strength

        # Sem padrão → sem voto
        if pattern == "none" or base_strength == 0.0:
            return SpecialistVote(
                self.name, None, 0.0, 50, "fragil", 0.0, False,
                ["Sem padrão de price action identificado"]
            )

        strength = base_strength
        direction = None
        reasons = [f"Padrão detectado: {pattern} (força base {base_strength:.2f})"]
        veto = False

        # ── Determinar direção pelo padrão ────────────────────────────────
        if pattern in _BULLISH_PATTERNS:
            direction = "CALL"
        elif pattern in _BEARISH_PATTERNS:
            direction = "PUT"
        elif pattern == "inside_bar":
            # Inside bar = compressão; segue tendência M1 com força reduzida
            direction = "CALL" if features.trend_m1 == "bull" else "PUT" if features.trend_m1 == "bear" else None
            strength *= 0.55
            reasons.append("Inside bar: compressão — segue tendência M1 com convicção reduzida")
        elif pattern == "doji":
            # Doji só vota em contexto de exaustão com rejeição confirmada
            if features.rejection and features.rsi >= 65:
                direction = "PUT"
                strength = 0.50
                reasons.append("Doji em sobrecompra com rejeição: sinal de reversão")
            elif features.rejection and features.rsi <= 35:
                direction = "CALL"
                strength = 0.50
                reasons.append("Doji em sobrevenda com rejeição: sinal de reversão")
            else:
                return SpecialistVote(
                    self.name, None, 0.0, 50, "fragil", 0.0, False,
                    ["Doji sem contexto de exaustão — sem voto"]
                )

        if direction is None:
            return SpecialistVote(
                self.name, None, 0.0, 50, "fragil", 0.0, False,
                [f"Padrão {pattern} sem direção operável"]
            )

        # ── Ajustes de contexto ───────────────────────────────────────────

        # Bônus: padrão alinhado com tendência M1 e M5
        if direction == "CALL" and features.trend_m1 == "bull" and features.trend_m5 == "bull":
            strength = min(1.0, strength + 0.18)
            reasons.append("Padrão alinhado com tendência M1+M5 bullish")
        elif direction == "PUT" and features.trend_m1 == "bear" and features.trend_m5 == "bear":
            strength = min(1.0, strength + 0.18)
            reasons.append("Padrão alinhado com tendência M1+M5 bearish")
        elif direction == "CALL" and features.trend_m1 == "bull":
            strength = min(1.0, strength + 0.08)
            reasons.append("Padrão alinhado com tendência M1 bullish")
        elif direction == "PUT" and features.trend_m1 == "bear":
            strength = min(1.0, strength + 0.08)
            reasons.append("Padrão alinhado com tendência M1 bearish")
        elif direction == "CALL" and features.trend_m1 == "bear":
            strength = max(0.0, strength - 0.22)
            reasons.append("Padrão contra-tendência M1 bearish")
        elif direction == "PUT" and features.trend_m1 == "bull":
            strength = max(0.0, strength - 0.22)
            reasons.append("Padrão contra-tendência M1 bullish")

        # Bônus: padrão em nível estrutural relevante
        if direction == "CALL" and features.near_swing_low:
            strength = min(1.0, strength + 0.18)
            reasons.append("Pin bar/engolfante bullish em swing low (suporte)")
        elif direction == "PUT" and features.near_swing_high:
            strength = min(1.0, strength + 0.18)
            reasons.append("Pin bar/engolfante bearish em swing high (resistência)")

        # Bônus: rejeição forte confirma o padrão
        if features.rejection_quality == "strong":
            strength = min(1.0, strength + 0.12)
            reasons.append("Rejeição forte confirma padrão de price action")

        # Penalidade: entrada tardia
        if features.late_entry_risk or features.moved_too_fast:
            strength = max(0.0, strength - 0.22)
            reasons.append("Penalidade: movimento já correu antes do sinal")

        # Penalidade: regime caótico
        if features.regime == "chaotic":
            strength = max(0.0, strength * 0.35)
            reasons.append("Penalidade severa: regime caótico invalida padrão")

        strength = round(max(0.0, strength), 2)
        confidence = int(max(50, min(92, 50 + strength * 44)))

        if strength >= 0.75:
            setup_quality = "premium"
        elif strength >= 0.55:
            setup_quality = "favoravel"
        elif strength >= 0.35:
            setup_quality = "monitorado"
        else:
            setup_quality = "fragil"

        return SpecialistVote(
            self.name,
            direction,
            strength,
            confidence,
            setup_quality,
            round(min(1.0, strength * 0.85), 2),
            veto,
            reasons,
        )
