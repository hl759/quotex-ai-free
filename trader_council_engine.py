from config import (
    DEFAULT_PAYOUT,
    EDGE_SEGMENT_MIN_TRADES,
    TRADER_COUNCIL_ACTIVE,
    TRADER_COUNCIL_SPECIALIST_LIMIT,
)
from trader_genome import build_trader_genome, asset_class_for, parse_session_bucket
from specialist_reputation_engine import SpecialistReputationEngine
from case_memory_engine import CaseMemoryEngine


class TraderCouncilEngine:
    def __init__(self):
        self.genome = build_trader_genome()
        self.reputation_engine = SpecialistReputationEngine()
        self.case_memory_engine = CaseMemoryEngine()

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _strategy_family(self, name):
        text = str(name or "none")
        if text.startswith("trend"):
            return "trend"
        if text.startswith("reversal"):
            return "reversal"
        if text.startswith("scalp"):
            return "scalp"
        return text.split("_")[0]

    def _base_direction(self, indicators):
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        if trend_m1 == "bull":
            return "CALL"
        if trend_m1 == "bear":
            return "PUT"
        rsi = self._safe_float(indicators.get("rsi"), 50.0)
        if rsi <= 40:
            return "CALL"
        if rsi >= 60:
            return "PUT"
        return None

    def _match_strength(self, specialist, asset, regime, session, family):
        score = 0.0
        score += 1.1 if specialist["regime_focus"] in (regime, "all") else 0.0
        score += 0.9 if specialist["asset_focus"] in (asset_class_for(asset), "all") else 0.0
        score += 0.8 if specialist["session_focus"] in (session, "any") else 0.0
        if specialist["role"] in (family, "capital_preserver", "no_trade", "risk_architect"):
            score += 1.1
        if specialist["role"] == "breakout" and family in ("trend", "scalp"):
            score += 0.7
        if specialist["role"] == "false_break" and family in ("trend", "scalp"):
            score += 0.6
        if specialist["role"] == "session_guard":
            score += 0.45
        return score

    def _role_opinion(self, role, indicators, direction, meta_context, environment_type, discernment_quality, anti_pattern_risk, memory_summary):
        breakout = bool(indicators.get("breakout", False))
        rejection = bool(indicators.get("rejection", False))
        volatility = bool(indicators.get("volatility", False))
        moved_fast = bool(indicators.get("moved_too_fast", False))
        is_sideways = bool(indicators.get("is_sideways", False))
        rsi = self._safe_float(indicators.get("rsi"), 50.0)
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        breakout_quality = str(meta_context.get("breakout_quality", "ausente"))
        conflict_type = str(meta_context.get("conflict_type", "neutro"))
        narrative = str(meta_context.get("market_narrative", "none"))
        expectancy_r = self._safe_float(memory_summary.get("expectancy_r"), 0.0)
        total_memory = int(memory_summary.get("total", 0) or 0)
        stance = "observe"
        strength = 0.0
        reasons = []
        implied_direction = direction

        if role == "trend":
            if trend_m1 in ("bull", "bear") and trend_m1 == trend_m5 and direction:
                stance = "support"
                strength = 1.0
                reasons.append("Trend veteran viu alinhamento forte")
            elif conflict_type == "destrutivo" or environment_type == "destructive":
                stance = "caution"
                strength = 0.8
                reasons.append("Trend veteran viu conflito destrutivo")
        elif role == "reversal":
            if rejection and ((rsi <= 37 and direction == "CALL") or (rsi >= 63 and direction == "PUT") or is_sideways):
                stance = "support"
                strength = 0.95
                reasons.append("Reversal veteran viu exaustão operável")
            elif trend_m1 == trend_m5 and trend_m1 in ("bull", "bear"):
                stance = "caution"
                strength = 0.75
                reasons.append("Reversal veteran teme trend maduro demais")
        elif role == "scalp":
            if volatility and not moved_fast and direction:
                stance = "support"
                strength = 0.85
                reasons.append("Scalp executor viu fluxo curto saudável")
            elif moved_fast:
                stance = "caution"
                strength = 0.7
                reasons.append("Scalp executor viu preço esticado")
        elif role == "breakout":
            if breakout and breakout_quality == "limpo" and conflict_type != "destrutivo":
                stance = "support"
                strength = 0.95
                reasons.append("Breakout hunter aprovou rompimento")
            elif breakout and breakout_quality == "armadilha":
                stance = "veto"
                strength = 1.0
                reasons.append("Breakout hunter leu armadilha")
        elif role == "false_break":
            if breakout_quality == "armadilha" or moved_fast or narrative in ("exaustao", "distribuicao"):
                stance = "veto"
                strength = 1.05
                reasons.append("False break detective vetou contexto suspeito")
        elif role == "session_guard":
            if environment_type in ("clean", "complex") and discernment_quality in ("premium", "bom"):
                stance = "support"
                strength = 0.55
                reasons.append("Session reader não viu ruído dominante")
            elif anti_pattern_risk in ("high", "critical"):
                stance = "caution"
                strength = 0.8
                reasons.append("Session reader viu micro estrutura tóxica")
        elif role == "volatility":
            if volatility and environment_type != "destructive":
                stance = "support"
                strength = 0.6
                reasons.append("Volatility reader aprovou energia operável")
            else:
                stance = "caution"
                strength = 0.65
                reasons.append("Volatility reader viu motor fraco")
        elif role == "capital_preserver":
            if environment_type == "destructive" or anti_pattern_risk in ("high", "critical"):
                stance = "veto"
                strength = 1.2
                reasons.append("Capital preserver defendeu patrimônio")
            elif discernment_quality not in ("premium", "bom"):
                stance = "caution"
                strength = 0.9
                reasons.append("Capital preserver exige leitura melhor")
        elif role == "no_trade":
            if environment_type == "destructive" or conflict_type == "destrutivo" or breakout_quality == "armadilha":
                stance = "veto"
                strength = 1.2
                reasons.append("No-trade guardian mandou ficar parado")
            elif expectancy_r < 0 and total_memory >= 8:
                stance = "caution"
                strength = 1.0
                reasons.append("No-trade guardian respeitou cicatriz histórica")
        elif role == "risk_architect":
            if total_memory >= EDGE_SEGMENT_MIN_TRADES and expectancy_r > 0:
                stance = "support"
                strength = 0.6
                reasons.append("Risk architect viu memória estatística aceitável")
            elif total_memory >= 8 and expectancy_r < 0:
                stance = "veto"
                strength = 0.95
                reasons.append("Risk architect vetou edge local negativo")

        if stance == "support" and total_memory >= 10 and expectancy_r < 0:
            stance = "caution"
            strength = max(strength, 0.9)
            reasons.append("Memória de casos rebaixou entusiasmo")

        return {
            "stance": stance,
            "strength": round(max(0.0, strength), 4),
            "direction": implied_direction,
            "reasons": reasons,
        }

    def _participant_payload(self, specialist, opinion, weight, reputation):
        return {
            "id": specialist["id"],
            "name": specialist["name"],
            "role": specialist["role"],
            "seniority": specialist["seniority"],
            "stance": opinion.get("stance", "observe"),
            "direction": opinion.get("direction"),
            "weight": round(weight, 4),
            "reputation_multiplier": reputation.get("reputation_multiplier", 1.0),
            "trades": reputation.get("trades", 0),
            "aligned_with_trade": False,
            "reasons": opinion.get("reasons", [])[:3],
        }

    def evaluate(self, asset, indicators, candidates, leader_name, final_direction, current_score, current_confidence, meta_context, environment_type, discernment_quality, anti_pattern_risk):
        if not TRADER_COUNCIL_ACTIVE:
            return {
                "active": False,
                "score_boost": 0.0,
                "confidence_shift": 0,
                "decision_cap": None,
                "direction_override": None,
                "quality": "desligado",
                "head_trader_action": "off",
                "reasons": ["Trader Council desligado por configuração"],
                "participants": [],
                "memory": {"summary": {"total": 0, "wins": 0, "losses": 0, "winrate": 0.0, "expectancy_r": 0.0, "avg_payout": DEFAULT_PAYOUT, "breakeven_winrate": round((1 / (1 + DEFAULT_PAYOUT)) * 100.0, 2)}, "scar_tissue": ["Council off"]},
                "summary": {},
            }

        regime = str(indicators.get("regime", "unknown"))
        session = parse_session_bucket(indicators.get("analysis_time"))
        family = self._strategy_family(leader_name)
        direction = final_direction or self._base_direction(indicators)

        memory = self.case_memory_engine.lookup(
            asset=asset,
            indicators={**indicators, "environment_type": environment_type},
            strategy_name=leader_name,
            direction=direction,
        )
        memory_summary = memory.get("summary", {})

        relevant = []
        for specialist in self.genome:
            match = self._match_strength(specialist, asset, regime, session, family)
            if match >= 2.4:
                relevant.append((match, specialist))
        relevant.sort(key=lambda x: (x[0], x[1].get("seniority_weight", 1.0)), reverse=True)
        selected = [spec for _, spec in relevant[: max(8, int(TRADER_COUNCIL_SPECIALIST_LIMIT or 24))]]

        if not selected:
            return {
                "active": False,
                "score_boost": 0.0,
                "confidence_shift": 0,
                "decision_cap": None,
                "direction_override": None,
                "quality": "neutro",
                "head_trader_action": "none",
                "reasons": ["Trader Council sem especialistas relevantes"],
                "participants": [],
                "memory": memory,
            }

        call_weight = 0.0
        put_weight = 0.0
        caution_weight = 0.0
        veto_weight = 0.0
        senior_support = 0.0
        senior_veto = 0.0
        participants = []

        for specialist in selected:
            opinion = self._role_opinion(
                role=specialist["role"],
                indicators=indicators,
                direction=direction,
                meta_context=meta_context,
                environment_type=environment_type,
                discernment_quality=discernment_quality,
                anti_pattern_risk=anti_pattern_risk,
                memory_summary=memory_summary,
            )
            if opinion.get("stance") == "observe" or opinion.get("strength", 0.0) <= 0:
                continue

            reputation = self.reputation_engine.reputation_for(specialist["id"])
            match = self._match_strength(specialist, asset, regime, session, family)
            weight = match * specialist.get("seniority_weight", 1.0) * opinion.get("strength", 0.0) * reputation.get("reputation_multiplier", 1.0)
            payload = self._participant_payload(specialist, opinion, weight, reputation)
            participants.append(payload)

            stance = opinion.get("stance")
            vote_direction = opinion.get("direction")
            if stance == "support":
                if vote_direction == "CALL":
                    call_weight += weight
                elif vote_direction == "PUT":
                    put_weight += weight
                if specialist["seniority"] == "principal":
                    senior_support += weight
            elif stance == "caution":
                caution_weight += weight
            elif stance == "veto":
                veto_weight += weight
                if specialist["seniority"] == "principal":
                    senior_veto += weight

        participants.sort(key=lambda x: x.get("weight", 0.0), reverse=True)
        participants = participants[:18]

        consensus_direction = None
        directional_gap = abs(call_weight - put_weight)
        if max(call_weight, put_weight) > 0:
            consensus_direction = "CALL" if call_weight >= put_weight else "PUT"

        support_weight = call_weight if consensus_direction == "CALL" else put_weight if consensus_direction == "PUT" else 0.0
        opposition_weight = put_weight if consensus_direction == "CALL" else call_weight if consensus_direction == "PUT" else 0.0

        decision_cap = None
        head_action = "observe"
        score_boost = 0.0
        confidence_shift = 0
        council_quality = "contested"
        reasons = []

        if memory_summary.get("total", 0) >= 8:
            reasons.append(
                f"Case memory: {memory_summary.get('winrate', 0.0)}% WR | {memory_summary.get('expectancy_r', 0.0)}R em {memory_summary.get('total', 0)} casos"
            )
        for note in memory.get("scar_tissue", [])[:3]:
            reasons.append(f"Scar tissue: {note}")

        if consensus_direction:
            reasons.append(f"Conselho favoreceu {consensus_direction} com peso {round(support_weight, 2)}")
        if opposition_weight > 0:
            reasons.append(f"Dissenso relevante com peso {round(opposition_weight, 2)}")
        if caution_weight > 0:
            reasons.append(f"Bloco cauteloso somou {round(caution_weight, 2)}")
        if veto_weight > 0:
            reasons.append(f"Vetos fortes somaram {round(veto_weight, 2)}")

        if senior_veto >= 9.2 or veto_weight >= max(13.2, support_weight * 1.75):
            decision_cap = "NAO_OPERAR"
            head_action = "block"
            score_boost = -0.35
            confidence_shift = -8
            council_quality = "capital_first"
            reasons.append("Head Trader: vetos seniores dominaram a mesa")
        elif support_weight <= 0 or (caution_weight + veto_weight) > (support_weight * 2.60):
            decision_cap = "OBSERVAR"
            head_action = "observe"
            score_boost = -0.12
            confidence_shift = -3
            council_quality = "fragile"
            reasons.append("Head Trader: consenso insuficiente para arriscar patrimônio")
        elif direction and consensus_direction and direction != consensus_direction and directional_gap >= 4.0:
            decision_cap = "OBSERVAR"
            head_action = "reconcile"
            score_boost = -0.10
            confidence_shift = -2
            reasons.append("Head Trader: direção original conflita com a mesa")
        elif support_weight >= max(4.4, opposition_weight * 1.15) and veto_weight <= 5.4 and senior_support >= 1.6:
            decision_cap = "ENTRADA_FORTE"
            head_action = "press"
            score_boost = 0.24
            confidence_shift = 5
            council_quality = "prime"
            reasons.append("Head Trader: mesa veterana aprovou agressão controlada")
        else:
            decision_cap = "ENTRADA_CAUTELA"
            head_action = "probe"
            score_boost = 0.10
            confidence_shift = 2
            council_quality = "measured"
            reasons.append("Head Trader: entrada permitida, mas em modo profissional")

        memory_total = int(memory_summary.get("total", 0) or 0)
        memory_expectancy = self._safe_float(memory_summary.get("expectancy_r"), 0.0)
        if memory_total >= 36 and memory_expectancy <= -0.12:
            score_boost -= 0.10
            confidence_shift -= 2
            if decision_cap == "ENTRADA_FORTE":
                decision_cap = "ENTRADA_CAUTELA"
            reasons.append("CRO interno: memória local negativa relevante reduziu agressividade")
        elif memory_total >= 20 and memory_expectancy <= -0.06:
            score_boost -= 0.04
            confidence_shift -= 1
            if decision_cap == "ENTRADA_FORTE":
                decision_cap = "ENTRADA_CAUTELA"
            reasons.append("CRO interno: memória local moderadamente negativa reduziu um pouco a agressividade")

        if environment_type == "destructive":
            decision_cap = "NAO_OPERAR"
            head_action = "block"
            score_boost = min(score_boost, -0.20)
            confidence_shift = min(confidence_shift, -5)
            council_quality = "capital_first"
            reasons.append("CRO interno: ambiente destrutivo sobrepôs a mesa")

        conflict_type = str(meta_context.get("conflict_type", "neutro"))
        premium_operable = (
            discernment_quality == "premium"
            and environment_type != "destructive"
            and anti_pattern_risk not in ("high", "critical")
            and conflict_type != "destrutivo"
        )
        hard_block = senior_veto >= 9.2 or veto_weight >= max(13.2, support_weight * 1.80)
        if premium_operable and decision_cap in ("NAO_OPERAR", "OBSERVAR") and not hard_block:
            if support_weight >= max(2.6, opposition_weight * 1.00):
                decision_cap = "ENTRADA_CAUTELA"
                head_action = "probe"
                score_boost = max(score_boost, 0.10)
                confidence_shift = max(confidence_shift, 2)
                council_quality = "measured"
                reasons.append("Head Trader: contexto premium operável evitou bloqueio excessivo")
            elif support_weight > 0:
                decision_cap = "ENTRADA_CAUTELA"
                head_action = "observe"
                score_boost = max(score_boost, 0.04)
                confidence_shift = max(confidence_shift, 1)
                council_quality = "measured"
                reasons.append("Head Trader: contexto premium manteve cautela em vez de veto")

        for item in participants:
            stance = item.get("stance")
            item["aligned_with_trade"] = (
                stance == "support" and item.get("direction") == consensus_direction
            )
            if stance in ("veto", "caution") and consensus_direction:
                item["aligned_with_trade"] = False

        return {
            "active": True,
            "quality": council_quality,
            "consensus_direction": consensus_direction,
            "directional_gap": round(directional_gap, 4),
            "support_weight": round(support_weight, 4),
            "opposition_weight": round(opposition_weight, 4),
            "caution_weight": round(caution_weight, 4),
            "veto_weight": round(veto_weight, 4),
            "senior_support_weight": round(senior_support, 4),
            "senior_veto_weight": round(senior_veto, 4),
            "score_boost": round(score_boost, 4),
            "confidence_shift": int(confidence_shift),
            "decision_cap": decision_cap,
            "direction_override": consensus_direction if consensus_direction and support_weight > opposition_weight * 1.4 and veto_weight < support_weight * 0.5 else None,
            "head_trader_action": head_action,
            "reasons": reasons,
            "participants": participants,
            "memory": memory,
            "summary": {
                "support_weight": round(support_weight, 4),
                "opposition_weight": round(opposition_weight, 4),
                "caution_weight": round(caution_weight, 4),
                "veto_weight": round(veto_weight, 4),
                "consensus_direction": consensus_direction,
                "quality": council_quality,
                "head_trader_action": head_action,
                "avg_payout_reference": round(DEFAULT_PAYOUT, 4),
            },
        }
