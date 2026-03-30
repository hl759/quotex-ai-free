import json
import os
from storage_paths import DATA_DIR, migrate_file

os.makedirs(DATA_DIR, exist_ok=True)
JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")
migrate_file(JOURNAL_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_journal.json")])


class AdaptiveBehavioralOrchestrationEngine:
    """
    Etapa 12 — Adaptive Behavioral Orchestration Engine

    Não adiciona nova camada de leitura.
    Apenas orquestra o comportamento com base nas camadas já existentes:
    - meta_context
    - veteran_discernment
    - environment transition
    - risk dominance

    Objetivo:
    - não deixar a IA rígida
    - não deixar a IA solta demais
    - resolver conflito entre leitura boa e ambiente ruim
    - liberar atuação controlada em imperfeição válida
    """

    def _load_journal(self):
        try:
            if os.path.exists(JOURNAL_FILE):
                with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
        return []

    def _hour_bucket(self, text):
        try:
            s = str(text or "").strip()
            if ":" not in s:
                return "unknown"
            hh = int(s.split(":")[0])
            if 0 <= hh <= 23:
                return f"{hh:02d}:00"
        except Exception:
            pass
        return "unknown"

    def _behavior_memory(self, asset, regime, analysis_time, environment_type):
        rows = self._load_journal()
        if not rows:
            return {
                "mode_hint": "neutral",
                "sample": 0,
                "winrate": 0.0,
                "reason": "Memória comportamental sem histórico relevante"
            }

        hour = self._hour_bucket(analysis_time)
        relevant = []

        for row in rows:
            result = str(row.get("result", "")).upper()
            if result not in ("WIN", "LOSS"):
                continue

            if str(row.get("asset", "")) != str(asset):
                continue

            score = 0

            if str(row.get("regime", "")) == str(regime):
                score += 2

            row_hour = self._hour_bucket(row.get("analysis_time"))
            if hour != "unknown" and row_hour == hour:
                score += 1

            if environment_type == "destructive" and str(row.get("regime", "")) in ("mixed", "chaotic", "sideways"):
                score += 1
            elif environment_type == "structured_chaos" and str(row.get("regime", "")) in ("mixed", "trend"):
                score += 1
            elif environment_type == "clean" and str(row.get("regime", "")) == "trend":
                score += 1

            if score >= 2:
                relevant.append(row)

        if len(relevant) < 12:
            # fallback leve por ativo, sem exagerar
            for row in rows:
                result = str(row.get("result", "")).upper()
                if result not in ("WIN", "LOSS"):
                    continue
                if str(row.get("asset", "")) == str(asset) and row not in relevant:
                    relevant.append(row)
                if len(relevant) >= 20:
                    break

        total = len(relevant)
        if total == 0:
            return {
                "mode_hint": "neutral",
                "sample": 0,
                "winrate": 0.0,
                "reason": "Memória comportamental sem histórico relevante"
            }

        wins = sum(1 for row in relevant if str(row.get("result", "")).upper() == "WIN")
        winrate = round((wins / total) * 100, 2)

        if winrate >= 60:
            mode_hint = "expand"
            reason = f"Memória comportamental favorece expansão ({winrate}%)"
        elif winrate <= 38:
            mode_hint = "protect"
            reason = f"Memória comportamental pede proteção ({winrate}%)"
        else:
            mode_hint = "neutral"
            reason = f"Memória comportamental neutra ({winrate}%)"

        return {
            "mode_hint": mode_hint,
            "sample": total,
            "winrate": winrate,
            "reason": reason
        }

    def evaluate(
        self,
        asset,
        regime,
        analysis_time,
        environment_type,
        discernment_quality,
        anti_pattern_risk,
        transition_probability,
        next_environment,
        risk_veto,
        risk_downgrade,
        meta_context,
        current_score,
        current_confidence,
    ):
        reasons = []
        score_boost = 0.0
        confidence_shift = 0
        frequency_limit = 1
        aggressiveness = "normal"
        acceptance_floor = "aceitavel"
        downgrade = None
        veto = False

        narrative = str(meta_context.get("market_narrative", "none"))
        trend_quality = str(meta_context.get("trend_quality", "neutra"))
        breakout_quality = str(meta_context.get("breakout_quality", "ausente"))
        conflict_type = str(meta_context.get("conflict_type", "neutro"))

        memory = self._behavior_memory(asset, regime, analysis_time, environment_type)
        reasons.append(memory["reason"])

        # 1) modo base
        if risk_veto or environment_type == "destructive":
            behavior_mode = "SURVIVAL"
        elif environment_type == "clean" and discernment_quality in ("premium", "bom") and anti_pattern_risk not in ("high", "medium"):
            behavior_mode = "EXPANSION"
        elif environment_type in ("complex", "structured_chaos") or transition_probability in ("medium", "high"):
            behavior_mode = "CAUTIOUS"
        else:
            behavior_mode = "BALANCED"

        # 2) memória comportamental ajusta, sem rigidez burra
        if memory["mode_hint"] == "expand":
            if behavior_mode == "BALANCED" and environment_type != "destructive":
                behavior_mode = "EXPANSION"
                reasons.append("Orquestração: memória liberou expansão")
            elif behavior_mode == "CAUTIOUS" and environment_type == "structured_chaos" and conflict_type != "destrutivo":
                behavior_mode = "BALANCED"
                reasons.append("Orquestração: memória suavizou cautela")
        elif memory["mode_hint"] == "protect":
            if behavior_mode == "EXPANSION":
                behavior_mode = "BALANCED"
                reasons.append("Orquestração: memória reduziu expansão")
            elif behavior_mode == "BALANCED":
                behavior_mode = "CAUTIOUS"
                reasons.append("Orquestração: memória elevou proteção")

        # 3) conflitos entre camadas
        if discernment_quality == "premium" and environment_type == "destructive":
            behavior_mode = "CAUTIOUS" if not risk_veto else "SURVIVAL"
            reasons.append("Orquestração: contexto premium contido por ambiente destrutivo")

        if conflict_type == "destrutivo" and breakout_quality == "armadilha":
            behavior_mode = "SURVIVAL"
            reasons.append("Orquestração: conflito destrutivo + armadilha")

        if narrative in ("distribuicao", "exaustao") and transition_probability == "high":
            behavior_mode = "SURVIVAL"
            reasons.append("Orquestração: narrativa tóxica com transição alta")

        # 4) parâmetros por modo
        if behavior_mode == "EXPANSION":
            score_boost += 0.10
            confidence_shift += 3
            frequency_limit = 2
            aggressiveness = "elevated"
            acceptance_floor = "aceitavel" if anti_pattern_risk not in ("high",) else "bom"
            reasons.append("Modo comportamental: EXPANSION")

        elif behavior_mode == "BALANCED":
            score_boost += 0.00
            confidence_shift += 0
            frequency_limit = 1
            aggressiveness = "normal"
            acceptance_floor = "aceitavel"
            reasons.append("Modo comportamental: BALANCED")

        elif behavior_mode == "CAUTIOUS":
            score_boost -= 0.08
            confidence_shift -= 2
            frequency_limit = 1
            aggressiveness = "reduced"
            acceptance_floor = "bom"
            reasons.append("Modo comportamental: CAUTIOUS")

            # Cautela não é bloqueio cego: permite edge imperfeito válido
            if (
                current_score >= 4.0
                and discernment_quality in ("premium", "bom")
                and conflict_type != "destrutivo"
                and anti_pattern_risk not in ("high",)
            ):
                downgrade = "CAUTELA"
                reasons.append("Orquestração: edge imperfeito mas válido mantido em cautela")
            elif current_score + score_boost < 3.0 or discernment_quality == "aceitavel":
                downgrade = "OBSERVAR"
                reasons.append("Orquestração: cautela rebaixa contexto marginal")

        else:  # SURVIVAL
            score_boost -= 0.16
            confidence_shift -= 4
            frequency_limit = 1
            aggressiveness = "minimal"
            acceptance_floor = "premium"
            reasons.append("Modo comportamental: SURVIVAL")

            # Sobrevivência continua defensiva, mas uma leitura excepcional pode passar em cautela.
            if (
                current_score >= 4.5
                and discernment_quality == "premium"
                and anti_pattern_risk not in ("high", "critical")
                and conflict_type != "destrutivo"
                and transition_probability != "high"
            ):
                downgrade = "CAUTELA"
                reasons.append("Orquestração final: sobrevivência liberou cautela premium")
            elif (
                current_score >= 4.0
                and discernment_quality in ("premium", "bom")
                and anti_pattern_risk not in ("high", "critical")
                and conflict_type != "destrutivo"
            ):
                downgrade = "OBSERVAR"
                reasons.append("Orquestração final: sobrevivência permitiu observação qualificada")
            else:
                veto = True
                reasons.append("Orquestração final: sobrevivência vetou a entrada")

        # 5) perigos absolutos
        if conflict_type == "destrutivo" and breakout_quality == "armadilha":
            veto = True
            reasons.append("Orquestração: conflito destrutivo + armadilha forçam veto")

        if narrative in ("distribuicao", "exaustao") and transition_probability == "high":
            veto = True
            reasons.append("Orquestração: narrativa tóxica com transição alta")

        # 6) respeitar o risk dominance
        if risk_downgrade == "OBSERVAR" and downgrade != "OBSERVAR":
            downgrade = "OBSERVAR"
            reasons.append("Orquestração: respeitando downgrade do risk dominance")
        elif risk_downgrade == "CAUTELA" and downgrade is None and behavior_mode in ("EXPANSION", "BALANCED"):
            downgrade = "CAUTELA"
            reasons.append("Orquestração: respeitando cautela do risk dominance")

        return {
            "behavior_mode": behavior_mode,
            "score_boost": round(score_boost, 2),
            "confidence_shift": int(confidence_shift),
            "frequency_limit": int(frequency_limit),
            "aggressiveness": aggressiveness,
            "acceptance_floor": acceptance_floor,
            "downgrade": downgrade,
            "veto": veto,
            "memory_sample": memory["sample"],
            "memory_winrate": memory["winrate"],
            "reasons": reasons,
        }
