class RiskDominanceEngine:
    """
    Dá prioridade dominante ao risco estrutural do ambiente e à transição.
    Objetivo:
    - impedir score técnico bonito em ambiente podre
    - diferenciar caos estruturado de ambiente destrutivo
    - rebaixar ou vetar com autoridade
    """

    def evaluate(self, environment_type, meta_context, transition_data, current_score, current_confidence):
        score_boost = 0.0
        confidence_shift = 0
        veto = False
        downgrade = None
        reasons = []

        trend_quality = str(meta_context.get("trend_quality", "neutra"))
        breakout_quality = str(meta_context.get("breakout_quality", "ausente"))
        conflict_type = str(meta_context.get("conflict_type", "neutro"))
        narrative = str(meta_context.get("market_narrative", "none"))

        transition_probability = str(transition_data.get("transition_probability", "low"))
        next_environment = str(transition_data.get("next_environment", "unknown"))

        if environment_type == "destructive":
            score_boost -= 0.35
            confidence_shift -= 6
            reasons.append("Risk dominance: ambiente destrutivo domina a decisão")

        elif environment_type == "structured_chaos":
            score_boost -= 0.05
            confidence_shift -= 1
            reasons.append("Risk dominance: caos estruturado exige operação seletiva")

        elif environment_type == "complex":
            score_boost -= 0.08
            confidence_shift -= 2
            reasons.append("Risk dominance: ambiente complexo reduz autoridade do setup")

        elif environment_type == "clean":
            reasons.append("Risk dominance: ambiente limpo sem penalização estrutural")

        if transition_probability == "high":
            score_boost -= 0.18
            confidence_shift -= 4
            reasons.append(f"Risk dominance: transição alta para {next_environment}")
        elif transition_probability == "medium":
            score_boost -= 0.08
            confidence_shift -= 2
            reasons.append(f"Risk dominance: transição média para {next_environment}")

        if conflict_type == "destrutivo":
            score_boost -= 0.18
            confidence_shift -= 4
            reasons.append("Risk dominance: conflito destrutivo tem prioridade")
        elif conflict_type == "transicional":
            score_boost -= 0.04
            reasons.append("Risk dominance: conflito transicional pede cautela")

        if breakout_quality == "armadilha":
            score_boost -= 0.18
            confidence_shift -= 4
            reasons.append("Risk dominance: breakout armadilha derruba convicção")
        elif breakout_quality == "duvidoso":
            score_boost -= 0.06
            reasons.append("Risk dominance: breakout duvidoso enfraquece o contexto")

        if trend_quality == "exausta":
            score_boost -= 0.14
            confidence_shift -= 3
            reasons.append("Risk dominance: tendência exausta pesa contra")
        elif trend_quality == "fragil":
            score_boost -= 0.05
            reasons.append("Risk dominance: tendência frágil reduz convicção")

        if narrative in ("distribuicao", "exaustao"):
            score_boost -= 0.12
            confidence_shift -= 3
            reasons.append(f"Risk dominance: narrativa de {narrative} é tóxica")
        elif narrative == "compressao_pre_breakout":
            reasons.append("Risk dominance: compressão não é veto, mas exige confirmação")

        projected_score = current_score + score_boost
        projected_confidence = current_confidence + confidence_shift

        # veto dominante
        if environment_type == "destructive" and transition_probability in ("medium", "high"):
            veto = True
            reasons.append("Risk dominance final: veto por deterioração estrutural")
        elif conflict_type == "destrutivo" and breakout_quality == "armadilha":
            veto = True
            reasons.append("Risk dominance final: veto por armadilha estrutural")
        elif projected_score < 2.0 and projected_confidence < 65:
            veto = True
            reasons.append("Risk dominance final: veto por perda de edge")

        # rebaixamento forte
        if not veto:
            if transition_probability == "high" or environment_type in ("complex", "structured_chaos"):
                downgrade = "CAUTELA"
                reasons.append("Risk dominance final: oportunidade rebaixada para cautela")
            if projected_score < 2.4:
                downgrade = "OBSERVAR"
                reasons.append("Risk dominance final: oportunidade rebaixada para observação")

        return {
            "score_boost": round(score_boost, 2),
            "confidence_shift": int(confidence_shift),
            "veto": veto,
            "downgrade": downgrade,
            "reasons": reasons,
        }
