from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from alpha_hive.core.clock import now_brazil
from alpha_hive.core.contracts import FinalDecision, MarketSnapshot
from alpha_hive.learning.learning_engine import LearningEngine


class MetaDecisionEngine:
    def __init__(self, learning_engine: LearningEngine | None = None):
        self.learning = learning_engine or LearningEngine()

    def _hour_bucket(self) -> str:
        return f"{now_brazil().hour:02d}:00"

    def _find_group(self, rows: List[Dict[str, Any]], key: str, value: str) -> Dict[str, Any]:
        for row in rows:
            if str(row.get(key, "")) == str(value):
                return row
        return {}

    def _context(self, decision: FinalDecision) -> Dict[str, Any]:
        features = dict(decision.features or {})
        trend_m1 = str(features.get("trend_m1", "unknown"))
        trend_m5 = str(features.get("trend_m5", "unknown"))
        return {
            "trend_m1": trend_m1,
            "trend_m5": trend_m5,
            "multi_tf_conflict": trend_m1 != trend_m5,
            "breakout_quality": features.get("breakout_quality", "unknown"),
            "rejection_quality": features.get("rejection_quality", "unknown"),
            "explosive_expansion": bool(features.get("explosive_expansion", False)),
            "late_entry_risk": bool(features.get("late_entry_risk", False)),
            "is_sideways": bool(features.get("is_sideways", False)),
            "trend_quality_signal": features.get("trend_quality_signal", "unknown"),
            "consensus_quality": decision.consensus_quality,
        }

    def _meta_components(self, decision: FinalDecision, snapshot: MarketSnapshot, audit_report: Dict[str, Any]) -> Dict[str, float]:
        features = dict(decision.features or {})
        asset_row = self._find_group(audit_report.get("by_asset", []), "asset", decision.asset)
        provider_row = self._find_group(audit_report.get("by_provider", []), "provider", decision.provider)
        hour_row = self._find_group(audit_report.get("by_hour", []), "hour", self._hour_bucket().split(":")[0])

        asset_bonus = 0.0
        if int(asset_row.get("total", 0) or 0) >= 10:
            asset_bonus += max(-0.22, min(0.22, float(asset_row.get("expectancy_r", 0.0) or 0.0) * 0.22))
            asset_bonus += max(-0.10, min(0.10, ((float(asset_row.get("winrate", 50.0) or 50.0) - 50.0) / 100.0) * 0.22))

        provider_bonus = 0.0
        if int(provider_row.get("total", 0) or 0) >= 8:
            provider_bonus += max(-0.12, min(0.12, float(provider_row.get("expectancy_r", 0.0) or 0.0) * 0.18))

        hour_bonus = 0.0
        if int(hour_row.get("total", 0) or 0) >= 8:
            hour_bonus += max(-0.10, min(0.10, float(hour_row.get("expectancy_r", 0.0) or 0.0) * 0.16))

        structure_penalty = 0.0
        structure_penalty += float(features.get("exhaustion_risk", 0.0) or 0.0) * 0.55
        structure_penalty += float(features.get("fake_move_risk", 0.0) or 0.0) * 0.42
        structure_penalty -= float(features.get("followthrough_bias", 0.0) or 0.0) * 0.28
        if str(features.get("regime_transition_state", "stable")) in ("transition", "exhaustion"):
            structure_penalty += 0.12
        if str(features.get("compression_state", "normal")) == "tight" and bool(features.get("breakout", False)):
            structure_penalty -= 0.05

        feed_penalty = 0.0
        feed_penalty += max(0.0, 0.75 - float(features.get("provider_confidence", 1.0) or 1.0)) * 0.35
        if "-cache" in str(snapshot.provider or ""):
            feed_penalty += 0.06

        context = self._context(decision)
        lead_specialist = str((decision.council or {}).get("top_specialists", ["trend"])[0])
        segment_adj = self.learning.segment_adjustment(
            asset=decision.asset,
            direction=str(decision.direction or "CALL"),
            regime=str(features.get("regime", "unknown")),
            specialist=lead_specialist,
            provider=str(decision.provider).split("-")[0],
            market_type=decision.market_type,
            hour_bucket=self._hour_bucket(),
            setup_quality=decision.setup_quality,
            extra_context=context,
        )

        opportunity_adj = self.learning.opportunity_adjustment(
            asset=decision.asset,
            direction=str(decision.direction or "CALL"),
            regime=str(features.get("regime", "unknown")),
            provider=str(decision.provider).split("-")[0],
            market_type=decision.market_type,
            hour_bucket=self._hour_bucket(),
            setup_quality=decision.setup_quality,
            extra_context=context,
        )

        return {
            "asset_bonus": round(asset_bonus, 3),
            "provider_bonus": round(provider_bonus, 3),
            "hour_bonus": round(hour_bonus, 3),
            "structure_penalty": round(max(0.0, structure_penalty), 3),
            "feed_penalty": round(max(0.0, feed_penalty), 3),
            "opportunity_bonus": round(float(opportunity_adj.get("score_bonus", 0.0) or 0.0), 3),
            "segment_bonus": round(float(segment_adj.get("score_boost", 0.0) or 0.0), 3),
        }

    def validate(self, decision: FinalDecision, snapshot: MarketSnapshot, audit_report: Dict[str, Any]) -> FinalDecision:
        out = deepcopy(decision)
        comps = self._meta_components(decision, snapshot, audit_report)

        meta_rank_score = (
            float(decision.score)
            + (float(decision.confidence) / 100.0)
            + comps["asset_bonus"]
            + comps["provider_bonus"]
            + comps["hour_bonus"]
            + comps["opportunity_bonus"]
            + (comps["segment_bonus"] * 0.35)
            - comps["structure_penalty"]
            - comps["feed_penalty"]
        )
        meta_rank_score = round(meta_rank_score, 3)

        features = dict(decision.features or {})
        meta_reasons: List[str] = []

        if comps["asset_bonus"] > 0.05:
            meta_reasons.append("Histórico do ativo favorece este contexto")
        if comps["hour_bonus"] > 0.04:
            meta_reasons.append("Faixa horária favorece esta leitura")
        if comps["structure_penalty"] >= 0.16:
            meta_reasons.append("Estrutura degradada pelo meta-filtro")
        if comps["feed_penalty"] >= 0.08:
            meta_reasons.append("Confiança do feed reduziu convicção")
        if comps["opportunity_bonus"] > 0.05:
            meta_reasons.append("Memória de oportunidade perdida favorece o contexto")

        dangerous = (
            float(features.get("exhaustion_risk", 0.0) or 0.0) >= 0.72
            or float(features.get("fake_move_risk", 0.0) or 0.0) >= 0.70
            or str(features.get("regime_transition_state", "stable")) == "exhaustion"
        )

        promotable = (
            decision.decision == "OBSERVAR"
            and decision.execution_permission != "BLOQUEADO"
            and meta_rank_score >= 5.25
            and not dangerous
            and decision.consensus_quality in ("measured", "prime")
        )

        if decision.decision == "ENTRADA_FORTE" and (dangerous or meta_rank_score < 5.35):
            out.decision = "ENTRADA_CAUTELA"
            out.execution_permission = "CAUTELA_OPERAVEL"
            meta_reasons.append("Meta-filtro rebaixou entrada forte para cautela")
        elif decision.decision == "ENTRADA_CAUTELA" and (dangerous or meta_rank_score < 4.55):
            out.decision = "OBSERVAR"
            out.execution_permission = "BLOQUEADO"
            out.state = "OBSERVE"
            out.suggested_stake = 0.0
            out.risk_pct = 0.0
            meta_reasons.append("Meta-filtro bloqueou entrada frágil")
        elif promotable:
            out.decision = "ENTRADA_CAUTELA"
            out.execution_permission = "CAUTELA_OPERAVEL"
            out.state = "CAUTION"
            meta_reasons.append("Meta-filtro encontrou oportunidade disciplinada")

        if comps["structure_penalty"] >= 0.12:
            out.confidence = max(50, out.confidence - int(round(comps["structure_penalty"] * 18)))
        if comps["asset_bonus"] > 0.05 and comps["feed_penalty"] < 0.08:
            out.confidence = min(95, out.confidence + 2)

        out.meta_rank_score = meta_rank_score
        out.meta_state = "strict" if dangerous else "positive" if meta_rank_score >= 5.4 else "neutral"
        out.meta_reasons = meta_reasons[:8]
        out.reasons = [*out.reasons, *meta_reasons][:40]
        return out
