class DecisionEngine:
    def __init__(self, learning):
        self.learning = learning

    def decide(self, asset, indicators):
        base_score = indicators.get("score", 0.0)
        direction = indicators.get("direction", "CALL")
        regime = indicators.get("regime", "unknown")

        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        rejection = indicators.get("rejection", False)
        breakout = indicators.get("breakout", False)
        pattern = indicators.get("pattern")
        volatility = indicators.get("volatility", False)
        moved_fast = indicators.get("moved_too_fast", False)
        is_sideways = indicators.get("is_sideways", False)
        rsi = indicators.get("rsi", 50)

        reasons = []

        # Base
        adjusted_score = float(base_score)
        reasons.append(f"Score base: {base_score}")

        # Aprendizado leve
        boost = 0.0
        try:
            boost = self.learning.get_score_boost(asset)
        except Exception:
            boost = 0.0

        adjusted_score += (boost * 0.7)
        reasons.append(f"Boost aprendizado: {round(boost, 2)}")

        # Perfil/calibração
        try:
            profile = self.learning.get_calibration_profile(asset)
        except Exception:
            profile = {
                "confidence_factor": 1.0,
                "aggressiveness": 1.0,
                "min_score": 3.0,
                "max_signals": 2,
                "mode": "base"
            }

        confidence_factor = profile.get("confidence_factor", 1.0)

        # Leitura mais humana de contexto
        if regime == "trend":
            adjusted_score += 0.45
            reasons.append("Regime: trend favorável")
        elif regime == "mixed":
            adjusted_score += 0.10
            reasons.append("Regime: mixed operável")
        elif regime == "sideways":
            adjusted_score -= 0.15
            reasons.append("Regime: sideways com cautela")
        elif regime == "chaotic":
            adjusted_score -= 1.0
            reasons.append("Regime: chaotic bloqueando")

        # Consenso entre timeframes
        if trend_m1 in ("bull", "bear") and trend_m5 in ("bull", "bear"):
            if trend_m1 == trend_m5:
                adjusted_score += 0.40
                reasons.append("M1 e M5 alinhados")
            else:
                adjusted_score -= 0.30
                reasons.append("Conflito entre M1 e M5")

        # Price action e contexto
        if rejection:
            adjusted_score += 0.25
            reasons.append("Rejeição relevante")

        if breakout:
            adjusted_score += 0.30
            reasons.append("Breakout limpo")

        if pattern in ("bullish", "bearish"):
            adjusted_score += 0.20
            reasons.append(f"Padrão {pattern}")

        if volatility:
            adjusted_score += 0.15
            reasons.append("Volatilidade saudável")

        if moved_fast:
            adjusted_score -= 0.20
            reasons.append("Preço já andou um pouco")

        if is_sideways:
            adjusted_score -= 0.10
            reasons.append("Zona de ruído")

        # RSI como refinamento leve
        if rsi <= 35 or rsi >= 65:
            adjusted_score += 0.10
            reasons.append("RSI em zona útil")
        elif 45 <= rsi <= 55:
            adjusted_score -= 0.05
            reasons.append("RSI neutro")

        # Filtro duro só para caos real
        if regime == "chaotic" and adjusted_score < 2.5:
            decision = "NAO_OPERAR"
            direction = None
            confidence = max(50, min(95, int((50 + adjusted_score * 10) * confidence_factor)))
            reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
            reasons.append("Modo: proteção em caos")
            return {
                "asset": asset,
                "decision": decision,
                "direction": direction,
                "score": round(adjusted_score, 2),
                "confidence": confidence,
                "regime": regime,
                "reasons": reasons
            }

        # ETAPA B:
        # OBSERVAR vira ação útil quando o contexto ajuda
        if adjusted_score >= 3.25:
            decision = "ENTRADA_FORTE"
        elif adjusted_score >= 2.35:
            decision = "ENTRADA_CAUTELA"
        elif adjusted_score >= 1.75:
            # promoção inteligente do OBSERVAR
            promote_to_caution = False

            if regime == "trend":
                if breakout or rejection or trend_m1 == trend_m5:
                    promote_to_caution = True

            elif regime == "mixed":
                if breakout or rejection or pattern in ("bullish", "bearish"):
                    promote_to_caution = True

            elif regime == "sideways":
                # em lateral só sobe com justificativa mais clara
                if rejection and pattern in ("bullish", "bearish"):
                    promote_to_caution = True

            if promote_to_caution:
                decision = "ENTRADA_CAUTELA"
                reasons.append("OBSERVAR promovido para CAUTELA")
            else:
                decision = "OBSERVAR"
        else:
            decision = "NAO_OPERAR"
            direction = None

        confidence = 50 + (adjusted_score * 10)
        confidence *= confidence_factor
        confidence = max(50, min(95, confidence))

        reasons.append(f"Regime final: {regime}")
        reasons.append(f"Score ajustado: {round(adjusted_score, 2)}")
        reasons.append("Modo: equilíbrio inteligente etapa B")

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(adjusted_score, 2),
            "confidence": int(confidence),
            "regime": regime,
            "reasons": reasons
        }
