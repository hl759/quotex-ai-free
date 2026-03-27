import json
import os

DATA_DIR = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
os.makedirs(DATA_DIR, exist_ok=True)
JOURNAL_FILE = os.path.join(DATA_DIR, "alpha_hive_journal.json")


class VeteranDiscernmentLayer:
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

    def _context_signature(self, asset, regime, strategy_name, meta):
        return {
            "asset": str(asset),
            "regime": str(regime),
            "strategy_name": str(strategy_name),
            "trend_quality": str(meta.get("trend_quality", "neutra")),
            "breakout_quality": str(meta.get("breakout_quality", "ausente")),
            "conflict_type": str(meta.get("conflict_type", "neutro")),
            "market_narrative": str(meta.get("market_narrative", "none")),
        }

    def _anti_pattern_memory(self, asset, regime, strategy_name, meta, analysis_time):
        sig = self._context_signature(asset, regime, strategy_name, meta)
        hour = self._hour_bucket(analysis_time)
        rows = []
        for t in self._valid_trades():
            if str(t.get("asset", "")) != sig["asset"]:
                continue
            similarity = 0
            if str(t.get("regime", "")) == sig["regime"]:
                similarity += 2
            if str(t.get("strategy_name", "")) == sig["strategy_name"]:
                similarity += 2
            if self._hour_bucket(t.get("analysis_time")) == hour and hour != "unknown":
                similarity += 1
            if sig["trend_quality"] == "exausta" and str(t.get("regime", "")) in ("mixed", "chaotic"):
                similarity += 1
            if sig["breakout_quality"] == "armadilha" and str(t.get("regime", "")) in ("mixed", "chaotic", "sideways"):
                similarity += 1
            if sig["conflict_type"] == "destrutivo" and str(t.get("regime", "")) in ("mixed", "chaotic"):
                similarity += 1
            if sig["market_narrative"] in ("distribuicao", "exaustao") and str(t.get("regime", "")) != "trend":
                similarity += 1
            rows.append({"result": self._result_value(t), "similarity": similarity})
        rows.sort(key=lambda x: x["similarity"], reverse=True)
        relevant = [r for r in rows if r["similarity"] >= 4]
        if len(relevant) < 12:
            relevant = rows[:max(12, min(50, len(rows)))]

        total = len(relevant)
        if total == 0:
            return {"trap_risk": "unknown", "sample": 0, "winrate": 0.0, "score_boost": 0.0, "confidence_shift": 0, "reason": "Anti-pattern memory sem histórico relevante"}

        wins = sum(1 for r in relevant if r["result"] == "WIN")
        winrate = round((wins / total) * 100, 2)

        if total >= 12 and winrate <= 34:
            return {"trap_risk": "high", "sample": total, "winrate": winrate, "score_boost": -0.18, "confidence_shift": -4, "reason": f"Anti-pattern memory detectou armadilha recorrente ({winrate}%)"}
        if total >= 12 and winrate <= 42:
            return {"trap_risk": "medium", "sample": total, "winrate": winrate, "score_boost": -0.08, "confidence_shift": -2, "reason": f"Anti-pattern memory detectou fragilidade recorrente ({winrate}%)"}
        if total >= 12 and winrate >= 66:
            return {"trap_risk": "low", "sample": total, "winrate": winrate, "score_boost": 0.08, "confidence_shift": 2, "reason": f"Anti-pattern memory validou contexto limpo ({winrate}%)"}
        return {"trap_risk": "neutral", "sample": total, "winrate": winrate, "score_boost": 0.0, "confidence_shift": 0, "reason": f"Anti-pattern memory neutra ({winrate}%)"}

    def evaluate(self, asset, strategy_name, indicators, current_score, current_confidence, meta_context):
        regime = indicators.get("regime", "unknown")
        analysis_time = indicators.get("analysis_time")

        score_boost = 0.0
        confidence_shift = 0
        reasons = []

        trend_quality = str(meta_context.get("trend_quality", "neutra"))
        breakout_quality = str(meta_context.get("breakout_quality", "ausente"))
        conflict_type = str(meta_context.get("conflict_type", "neutro"))
        market_narrative = str(meta_context.get("market_narrative", "none"))

        if trend_quality == "forte":
            score_boost += 0.10
            confidence_shift += 2
            reasons.append("Discernimento: contexto estrutural forte")
        elif trend_quality == "fragil":
            score_boost -= 0.05
            reasons.append("Discernimento: contexto estrutural frágil")
        elif trend_quality == "exausta":
            score_boost -= 0.14
            confidence_shift -= 3
            reasons.append("Discernimento: tendência cansada")

        if breakout_quality == "limpo":
            score_boost += 0.08
            reasons.append("Discernimento: breakout limpo")
        elif breakout_quality == "duvidoso":
            score_boost -= 0.05
            reasons.append("Discernimento: breakout duvidoso")
        elif breakout_quality == "armadilha":
            score_boost -= 0.16
            confidence_shift -= 3
            reasons.append("Discernimento: risco de armadilha")

        if conflict_type == "util":
            score_boost += 0.04
            reasons.append("Discernimento: conflito útil")
        elif conflict_type == "transicional":
            score_boost -= 0.02
            reasons.append("Discernimento: conflito transicional")
        elif conflict_type == "destrutivo":
            score_boost -= 0.14
            confidence_shift -= 3
            reasons.append("Discernimento: conflito destrutivo")

        if market_narrative == "expansao":
            score_boost += 0.08
            reasons.append("Discernimento: narrativa de expansão")
        elif market_narrative == "compressao_pre_breakout":
            score_boost += 0.06
            reasons.append("Discernimento: compressão promissora")
        elif market_narrative == "acumulacao":
            score_boost += 0.02
            reasons.append("Discernimento: acumulação observada")
        elif market_narrative == "distribuicao":
            score_boost -= 0.10
            confidence_shift -= 2
            reasons.append("Discernimento: distribuição/ruído")
        elif market_narrative == "exaustao":
            score_boost -= 0.14
            confidence_shift -= 3
            reasons.append("Discernimento: narrativa de exaustão")

        anti = self._anti_pattern_memory(asset, regime, strategy_name, meta_context, analysis_time)
        score_boost += anti["score_boost"]
        confidence_shift += anti["confidence_shift"]
        reasons.append(anti["reason"])

        final_score = current_score + score_boost
        final_conf = current_confidence + confidence_shift

        if anti["trap_risk"] == "high" and final_score < 3.8:
            quality = "vetado"; veto = True; reasons.append("Discernimento final: contexto vetado")
        elif final_score >= 4.8 and final_conf >= 82 and anti["trap_risk"] != "high" and breakout_quality != "armadilha" and conflict_type != "destrutivo":
            quality = "premium"; veto = False; reasons.append("Discernimento final: contexto premium")
        elif final_score >= 4.0 and final_conf >= 75 and conflict_type != "destrutivo":
            quality = "bom"; veto = False; reasons.append("Discernimento final: contexto bom")
        elif final_score >= 3.0 and anti["trap_risk"] not in ("high",):
            quality = "aceitavel"; veto = False; reasons.append("Discernimento final: contexto aceitável")
        elif final_score >= 2.2:
            quality = "duvidoso"; veto = False; reasons.append("Discernimento final: contexto duvidoso")
        else:
            quality = "vetado"; veto = True; reasons.append("Discernimento final: contexto vetado")

        return {
            "score_boost": round(score_boost, 2),
            "confidence_shift": int(confidence_shift),
            "quality": quality,
            "veto": veto,
            "anti_pattern_risk": anti["trap_risk"],
            "anti_pattern_sample": anti["sample"],
            "anti_pattern_winrate": anti["winrate"],
            "reasons": reasons,
        }
