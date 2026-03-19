class DecisionEngine:
    def __init__(self, learning_engine):
        self.learning = learning_engine

    def decide(self, asset, indicators):
        score = 0.0
        reasons = []
        direction = None

        trend_m1 = indicators.get("trend_m1") or indicators.get("trend") or "neutral"
        trend_m5 = indicators.get("trend_m5") or "neutral"
        rsi = indicators.get("rsi", 50)
        regime = indicators.get("regime", "unknown")
        moved_fast = indicators.get("moved_too_fast", False)
        sideways = indicators.get("is_sideways", False)
        pattern = indicators.get("pattern")
        breakout = indicators.get("breakout", False)
        rejection = indicators.get("rejection", False)
        volatility = indicators.get("volatility", False)

        # Direção base
        if trend_m1 in ("bull", "bear"):
            direction = "CALL" if trend_m1 == "bull" else "PUT"
            score += 1.6
            reasons.append("Tendência M1 definida")

        # Alinhamento estrutural
        if trend_m5 in ("bull", "bear"):
            if trend_m5 == trend_m1:
                score += 2.2
                reasons.append("M1 e M5 alinhados")
            else:
                score -= 1.2
                reasons.append("Conflito entre M1 e M5")

        # RSI balanceado
        if direction == "CALL" and rsi <= 38:
            score += 1.0
            reasons.append("RSI favorece alta")
        elif direction == "PUT" and rsi >= 62:
            score += 1.0
            reasons.append("RSI favorece queda")
        elif 46 <= rsi <= 54:
            score -= 0.2
            reasons.append("RSI neutro")

        # Price action
        if pattern == "bullish" and direction == "CALL":
            score += 0.7
            reasons.append("Padrão bullish")
        elif pattern == "bearish" and direction == "PUT":
            score += 0.7
            reasons.append("Padrão bearish")

        if breakout:
            score += 0.8
            reasons.append("Breakout confirmado")

        if rejection:
            score += 0.5
            reasons.append("Rejeição relevante")

        # Contexto de mercado balanceado
        if regime == "trend":
            score += 1.3
            reasons.append("Mercado em tendência")
        elif regime == "sideways":
            score -= 1.0
            reasons.append("Mercado lateral")
        elif regime == "chaotic":
            score -= 1.6
            reasons.append("Mercado caótico")
        elif regime == "mixed":
            score += 0.2
            reasons.append("Mercado misto operável")

        if volatility:
            score += 0.4
            reasons.append("Volatilidade saudável")

        # Evita entrar tarde, mas sem travar demais
        if moved_fast:
            score -= 0.8
            reasons.append("Preço já andou um pouco")

        if sideways:
            score -= 0.7
            reasons.append("Zona de ruído")

        # Aprendizado adaptativo
        try:
            bonus, learning_reason = self.learning.get_adaptive_bonus(asset)
            score += bonus
            if learning_reason:
                reasons.append(learning_reason)
        except Exception:
            pass

        # Fase ruim recente do ativo
        try:
            if self.learning.should_pause_asset_temporarily(asset):
                score -= 1.5
                reasons.append("Ativo em fase ruim recente")
        except Exception:
            pass

        # Rigor dinâmico leve
        try:
            rigor_penalty = self.learning.get_rigor_penalty()
            if rigor_penalty:
                score -= min(rigor_penalty, 0.6)
                reasons.append("Modo de cautela ativo")
        except Exception:
            pass

        if score < 0:
            score = 0

        # Mais equilibrado
        if score >= 5.4:
            decision = "ENTRADA_FORTE"
        elif score >= 3.6:
            decision = "ENTRADA_CAUTELA"
        else:
            decision = "NAO_OPERAR"
            direction = None

        confidence = int(min(95, max(54, 50 + score * 7)))

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(score, 2),
            "confidence": confidence,
            "reasons": reasons,
            "regime": regime
        }
