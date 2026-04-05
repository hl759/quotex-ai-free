
class StrategyVariantsEngine:
    def _clone(self, base, variant_name, score_delta=0.0, confidence_delta=0, extra_reason=None):
        item = dict(base)
        item["strategy"] = variant_name
        item["score"] = round(max(0.0, float(base.get("score", 0.0)) + score_delta), 2)
        item["confidence"] = int(max(50, min(95, int(base.get("confidence", 50)) + confidence_delta)))
        reasons = list(base.get("reasons", []))
        if extra_reason:
            reasons.append(extra_reason)
        item["reasons"] = reasons
        item["valid"] = item["score"] >= 1.2 and item.get("direction") is not None
        item["base_strategy"] = base.get("base_strategy", base.get("strategy", "none"))
        return item

    def _trend_variants(self, base, indicators):
        out = [self._clone(base, "trend_base", 0.0, 0, "Variante base de tendência")]
        rsi = indicators.get("rsi", 50)
        breakout = indicators.get("breakout", False)
        moved_fast = indicators.get("moved_too_fast", False)
        regime = indicators.get("regime", "unknown")
        trend_m1 = indicators.get("trend_m1", indicators.get("trend", "neutral"))
        trend_m5 = indicators.get("trend_m5", "neutral")
        if breakout:
            out.append(self._clone(base, "trend_breakout", 0.18, 2, "Variante breakout favorecida"))
        if (trend_m1 == "bull" and rsi <= 48) or (trend_m1 == "bear" and rsi >= 52):
            out.append(self._clone(base, "trend_pullback", 0.14, 1, "Variante pullback favorecida"))
        if regime in ("mixed", "sideways") or moved_fast:
            out.append(self._clone(base, "trend_defensive", -0.08, 0, "Variante defensiva de tendência"))
        if trend_m1 == trend_m5 and trend_m1 in ("bull", "bear"):
            out.append(self._clone(base, "trend_aligned", 0.12, 1, "Variante com alinhamento forte"))
        return out

    def _reversal_variants(self, base, indicators):
        out = [self._clone(base, "reversal_base", 0.0, 0, "Variante base de reversão")]
        rsi = indicators.get("rsi", 50)
        rejection = indicators.get("rejection", False)
        regime = indicators.get("regime", "unknown")
        pattern = indicators.get("pattern")
        if rejection:
            out.append(self._clone(base, "reversal_rejection_focus", 0.16, 1, "Variante focada em rejeição"))
        if rsi <= 32 or rsi >= 68:
            out.append(self._clone(base, "reversal_rsi_extreme", 0.18, 2, "Variante RSI extremo favorecida"))
        if regime == "sideways":
            out.append(self._clone(base, "reversal_sideways", 0.12, 1, "Variante especializada em sideways"))
        if pattern in ("bullish", "bearish"):
            out.append(self._clone(base, "reversal_pattern", 0.10, 1, "Variante com padrão confirmado"))
        return out

    def _scalp_variants(self, base, indicators):
        out = [self._clone(base, "scalp_base", 0.0, 0, "Variante base de scalp")]
        breakout = indicators.get("breakout", False)
        volatility = indicators.get("volatility", False)
        moved_fast = indicators.get("moved_too_fast", False)
        regime = indicators.get("regime", "unknown")
        if volatility and breakout:
            out.append(self._clone(base, "scalp_fast", 0.16, 2, "Variante rápida favorecida"))
        if not moved_fast:
            out.append(self._clone(base, "scalp_low_noise", 0.10, 1, "Variante com menor ruído"))
        if regime == "sideways":
            out.append(self._clone(base, "scalp_range", 0.08, 1, "Variante especializada em range curto"))
        return out

    def expand(self, asset, indicators, base_candidates):
        variants = []
        for base in base_candidates:
            if not base.get("valid"):
                continue
            strategy_name = base.get("strategy", "none")
            base = dict(base)
            base["base_strategy"] = strategy_name
            if strategy_name == "trend":
                variants.extend(self._trend_variants(base, indicators))
            elif strategy_name == "reversal":
                variants.extend(self._reversal_variants(base, indicators))
            elif strategy_name == "scalp":
                variants.extend(self._scalp_variants(base, indicators))
            else:
                variants.append(base)
        best = {}
        for item in variants:
            key = item.get("strategy", "none")
            if key not in best or float(item.get("score", 0.0)) > float(best[key].get("score", 0.0)):
                best[key] = item
        rows = list(best.values())
        rows.sort(key=lambda x: (x.get("score", 0.0), x.get("confidence", 0)), reverse=True)
        return rows
