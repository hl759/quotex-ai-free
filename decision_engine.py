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
            score += 1.7
            reasons.append("Tendência M1 definida")

        # Estrutura
        if trend_m5 in ("bull", "bear"):
            if trend_m5 == trend_m1:
                score += 2.4
                reasons.append("M1 e M5 alinhados")
            else:
                score -= 1.0
                reasons.append("Conflito entre M1 e M5")

        # RSI mais solto, mas ainda inteligente
        if direction == "CALL" and rsi <= 40:
            score += 1.1
            reasons.append("RSI favorece alta")
        elif direction == "PUT" and rsi >= 60:
            score += 1.1
            reasons.append("RSI favorece queda")
        elif 46 <= rsi <= 54:
            score -= 0.15
            reasons.append("RSI neutro")

        # Price action
        if pattern == "bullish" and direction == "CALL":
            score += 0.8
            reasons.append("Padrão bullish")
        elif pattern == "bearish" and direction == "PUT":
            score += 0.8
            reasons.append("Padrão bearish")

        if breakout:
            score += 0.9
            reasons.append("Breakout confirmado")

        if rejection:
            score += 0.6
            reasons.append("Rejeição relevante")

        # Contexto de mercado em modo consistente / semi-agressivo leve
        if regime == "trend":
            score += 1.4
            reasons.append("Mercado em tendência")
        elif regime == "sideways":
            score -= 0.8
            reasons.append("Mercado lateral")
        elif regime == "chaotic":
            score -= 1.8
            reasons.append("Mercado caótico")
        elif regime == "mixed":
            score += 0.35
            reasons.append("Mercado misto operável")

        if volatility:
            score += 0.45
            reasons.append("Volatilidade saudável")

        # Timing: penaliza, mas não trava demais
        if moved_fast:
            score -= 0.55
            reasons.append("Preço já andou um pouco")

        if sideways:
            score -= 0.5
            reasons.append("Zona de ruído")

        # Aprendizado adaptativo
        try:
            bonus, learning_reason = self.learning.get_adaptive_bonus(asset)
            score += bonus
            if learning_reason:
                reasons.append(learning_reason)
        except Exception:
            pass

        # Ativo em fase ruim: reduz, mas sem matar totalmente
        try:
            if self.learning.should_pause_asset_temporarily(asset):
                score -= 1.2
                reasons.append("Ativo em fase ruim recente")
        except Exception:
            pass

        # Rigor leve
        try:
            rigor_penalty = self.learning.get_rigor_penalty()
            if rigor_penalty:
                score -= min(rigor_penalty, 0.45)
                reasons.append("Modo de cautela ativo")
        except Exception:
            pass

        if score < 0:
            score = 0

        # Semi-agressivo leve: facilita cautela, mantém forte exigente
        if score >= 5.1:
            decision = "ENTRADA_FORTE"
        elif score >= 3.1:
            decision = "ENTRADA_CAUTELA"
        else:
            decision = "NAO_OPERAR"
            direction = None

        confidence = int(min(96, max(55, 51 + score * 7)))

        return {
            "asset": asset,
            "decision": decision,
            "direction": direction,
            "score": round(score, 2),
            "confidence": confidence,
            "reasons": reasons,
            "regime": regime
        }
