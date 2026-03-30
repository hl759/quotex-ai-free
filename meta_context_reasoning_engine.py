import json
import os
from storage_paths import DATA_DIR, migrate_file

os.makedirs(DATA_DIR, exist_ok=True)
JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")
migrate_file(JOURNAL_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_journal.json")])


class MetaContextReasoningEngine:
    """
    Camada semântica de leitura de mercado.
    Não usa regras rígidas de bloqueio; apenas interpreta e ajusta score/confiança.
    Aprende com o histórico do journal por narrativa/qualidade/contexto.
    """

    def _load_journal(self):
        try:
            if os.path.exists(JOURNAL_FILE):
                with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
        except Exception:
            pass
        return []

    def _result_value(self, row):
        return str(row.get("result", "")).upper()

    def _valid_trades(self):
        return [t for t in self._load_journal() if self._result_value(t) in ("WIN", "LOSS")]

    def _hour_bucket(self, analysis_time):
        try:
            text = str(analysis_time or "").strip()
            if ":" not in text:
                return "unknown"
            hh = int(text.split(":")[0])
            return f"{hh:02d}:00" if 0 <= hh <= 23 else "unknown"
        except Exception:
            return "unknown"

    def infer_meta_context(self, indicators):
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        regime = indicators.get("regime", "unknown")
        breakout = bool(indicators.get("breakout", False))
        rejection = bool(indicators.get("rejection", False))
        volatility = bool(indicators.get("volatility", False))
        moved_fast = bool(indicators.get("moved_too_fast", False))
        is_sideways = bool(indicators.get("is_sideways", False))
        pattern = indicators.get("pattern")
        rsi = float(indicators.get("rsi", 50) or 50)

        # narrative
        if breakout and volatility and not moved_fast and regime in ("trend", "mixed"):
            market_narrative = "expansao"
        elif is_sideways and volatility and breakout:
            market_narrative = "compressao_pre_breakout"
        elif is_sideways and rejection and not breakout:
            market_narrative = "acumulacao"
        elif moved_fast and rejection and regime != "trend":
            market_narrative = "exaustao"
        elif is_sideways and not volatility:
            market_narrative = "distribuicao"
        else:
            market_narrative = "transicao"

        # trend quality
        if trend_m1 in ("bull", "bear") and trend_m5 == trend_m1 and not moved_fast and regime == "trend":
            trend_quality = "forte"
        elif trend_m1 in ("bull", "bear") and moved_fast:
            trend_quality = "exausta"
        elif trend_m1 in ("bull", "bear"):
            trend_quality = "fragil"
        else:
            trend_quality = "neutra"

        # breakout quality
        if breakout and volatility and not moved_fast and trend_m1 == trend_m5 and trend_m1 in ("bull", "bear"):
            breakout_quality = "limpo"
        elif breakout and (moved_fast or regime == "chaotic"):
            breakout_quality = "armadilha"
        elif breakout:
            breakout_quality = "duvidoso"
        else:
            breakout_quality = "ausente"

        # conflict type
        if trend_m1 in ("bull", "bear") and trend_m5 in ("bull", "bear") and trend_m1 != trend_m5:
            if breakout or pattern in ("bullish", "bearish"):
                conflict_type = "transicional"
            else:
                conflict_type = "destrutivo"
        elif trend_m1 == trend_m5 and trend_m1 in ("bull", "bear"):
            conflict_type = "util"
        else:
            conflict_type = "neutro"

        return {
            "market_narrative": market_narrative,
            "trend_quality": trend_quality,
            "breakout_quality": breakout_quality,
            "conflict_type": conflict_type,
            "regime": regime,
        }

    def _match_rows(self, asset, strategy_name, analysis_time, meta_context):
        hour = self._hour_bucket(analysis_time)
        rows = []
        for t in self._valid_trades():
            if str(t.get("asset", "")) != str(asset):
                continue
            similarity = 0
            if str(t.get("strategy_name", "none")) == str(strategy_name):
                similarity += 3
            if self._hour_bucket(t.get("analysis_time")) == hour and hour != "unknown":
                similarity += 1
            if str(t.get("regime", "unknown")) == str(meta_context.get("regime", "unknown")):
                similarity += 2
            # weak semantic matching using tags previously inferable from regime/structure
            if meta_context.get("trend_quality") == "forte" and str(t.get("regime", "")) == "trend":
                similarity += 1
            if meta_context.get("market_narrative") in ("compressao_pre_breakout", "expansao") and str(t.get("regime", "")) in ("trend", "mixed"):
                similarity += 1
            rows.append({"result": self._result_value(t), "similarity": similarity})
        rows.sort(key=lambda x: x["similarity"], reverse=True)
        return rows

    def _historical_adjustment(self, asset, strategy_name, analysis_time, meta_context):
        rows = self._match_rows(asset, strategy_name, analysis_time, meta_context)
        if not rows:
            return {"score_boost": 0.0, "confidence_shift": 0, "history_reason": "Meta-contexto sem histórico", "sample": 0, "winrate": 0.0}

        relevant = [r for r in rows if r["similarity"] >= 3]
        if len(relevant) < 10:
            relevant = rows[:max(10, min(40, len(rows)))]

        total = len(relevant)
        wins = sum(1 for r in relevant if r["result"] == "WIN")
        winrate = round((wins / total) * 100, 2) if total > 0 else 0.0

        if total < 10:
            return {"score_boost": 0.0, "confidence_shift": 0, "history_reason": "Meta-contexto com pouca amostra", "sample": total, "winrate": winrate}
        if winrate >= 68:
            return {"score_boost": 0.16, "confidence_shift": 3, "history_reason": f"Meta-contexto historicamente favorável ({winrate}%)", "sample": total, "winrate": winrate}
        if winrate <= 38:
            return {"score_boost": -0.12, "confidence_shift": -3, "history_reason": f"Meta-contexto historicamente fraco ({winrate}%)", "sample": total, "winrate": winrate}
        return {"score_boost": 0.0, "confidence_shift": 0, "history_reason": f"Meta-contexto historicamente neutro ({winrate}%)", "sample": total, "winrate": winrate}

    def get_adjustment(self, asset, strategy_name, indicators, analysis_time=None):
        meta = self.infer_meta_context(indicators)

        score_boost = 0.0
        confidence_shift = 0
        reasons = []

        narrative = meta["market_narrative"]
        trend_quality = meta["trend_quality"]
        breakout_quality = meta["breakout_quality"]
        conflict_type = meta["conflict_type"]

        if narrative == "compressao_pre_breakout":
            score_boost += 0.10
            confidence_shift += 1
            reasons.append("Narrativa: compressão pré-breakout")
        elif narrative == "expansao":
            score_boost += 0.12
            confidence_shift += 2
            reasons.append("Narrativa: expansão saudável")
        elif narrative == "acumulacao":
            score_boost += 0.06
            reasons.append("Narrativa: acumulação observada")
        elif narrative == "distribuicao":
            score_boost -= 0.06
            confidence_shift -= 1
            reasons.append("Narrativa: distribuição/ruído")
        elif narrative == "exaustao":
            score_boost -= 0.10
            confidence_shift -= 2
            reasons.append("Narrativa: exaustão")

        if trend_quality == "forte":
            score_boost += 0.10
            confidence_shift += 2
            reasons.append("Qualidade de tendência: forte")
        elif trend_quality == "fragil":
            score_boost -= 0.03
            reasons.append("Qualidade de tendência: frágil")
        elif trend_quality == "exausta":
            score_boost -= 0.10
            confidence_shift -= 2
            reasons.append("Qualidade de tendência: exausta")

        if breakout_quality == "limpo":
            score_boost += 0.08
            confidence_shift += 1
            reasons.append("Breakout: limpo")
        elif breakout_quality == "duvidoso":
            score_boost -= 0.02
            reasons.append("Breakout: duvidoso")
        elif breakout_quality == "armadilha":
            score_boost -= 0.12
            confidence_shift -= 2
            reasons.append("Breakout: armadilha")

        if conflict_type == "util":
            score_boost += 0.05
            reasons.append("Conflito: útil")
        elif conflict_type == "transicional":
            reasons.append("Conflito: transicional")
        elif conflict_type == "destrutivo":
            score_boost -= 0.10
            confidence_shift -= 2
            reasons.append("Conflito: destrutivo")

        hist = self._historical_adjustment(asset, strategy_name, analysis_time, meta)
        score_boost += hist["score_boost"]
        confidence_shift += hist["confidence_shift"]
        reasons.append(hist["history_reason"])

        return {
            "score_boost": round(score_boost, 2),
            "confidence_shift": int(confidence_shift),
            "reasons": reasons,
            "meta_context": meta,
            "history_sample": hist["sample"],
            "history_winrate": hist["winrate"],
        }
