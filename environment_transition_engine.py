class EnvironmentTransitionEngine:
    def analyze_transition(self, meta):
        trend = meta.get("trend_quality")
        breakout = meta.get("breakout_quality")
        conflict = meta.get("conflict_type")
        narrative = meta.get("market_narrative")

        transition_probability = "low"
        next_env = "unknown"
        reason = []

        if trend == "forte" and breakout == "limpo":
            if conflict == "transicional":
                transition_probability = "medium"
                next_env = "complex"
                reason.append("Possível perda de alinhamento")

        if trend == "forte" and narrative == "expansao":
            transition_probability = "medium"
            next_env = "exaustao"
            reason.append("Movimento pode estar esticado")

        if narrative == "compressao_pre_breakout":
            transition_probability = "high"
            next_env = "expansao"
            reason.append("Compressão indicando possível explosão")

        if breakout == "armadilha" or conflict == "destrutivo":
            transition_probability = "high"
            next_env = "destructive"
            reason.append("Estrutura fraca indicando deterioração")

        return {
            "transition_probability": transition_probability,
            "next_environment": next_env,
            "reason": reason
        }
