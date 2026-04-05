
import os


class CapitalMindEngine:
    """
    Trata a banca como patrimônio próprio:
    - preserva primeiro
    - cresce progressivamente
    - ajusta risco por contexto, confiança e fase da curva
    - funciona de forma neutra se não houver capital informado
    """

    def __init__(self):
        self.default_capital = self._float_env("ALPHA_HIVE_CAPITAL", 0.0)
        self.default_daily_target_pct = self._float_env("ALPHA_HIVE_DAILY_TARGET_PCT", 2.0)
        self.default_daily_stop_pct = self._float_env("ALPHA_HIVE_DAILY_STOP_PCT", 3.0)

    def _float_env(self, name, default):
        try:
            return float(os.environ.get(name, default))
        except Exception:
            return float(default)

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _phase(self, capital, peak_capital, daily_pnl):
        if capital <= 0:
            return "neutral"

        drawdown_pct = 0.0
        if peak_capital and peak_capital > 0:
            drawdown_pct = max(0.0, (peak_capital - capital) / peak_capital) * 100

        if drawdown_pct >= 8 or daily_pnl <= -(capital * 0.03):
            return "defensive"
        if daily_pnl >= (capital * 0.02):
            return "expansion"
        return "neutral"

    def get_plan(self, asset, adjusted_score, confidence, indicators=None):
        indicators = indicators or {}

        capital = self._safe_float(indicators.get("capital_current", self.default_capital), 0.0)
        peak_capital = self._safe_float(indicators.get("capital_peak", capital), capital)
        daily_pnl = self._safe_float(indicators.get("daily_pnl", 0.0), 0.0)
        streak = int(self._safe_float(indicators.get("streak", 0), 0))
        daily_target_pct = self._safe_float(indicators.get("daily_target_pct", self.default_daily_target_pct), self.default_daily_target_pct)
        daily_stop_pct = self._safe_float(indicators.get("daily_stop_pct", self.default_daily_stop_pct), self.default_daily_stop_pct)

        phase = self._phase(capital, peak_capital, daily_pnl)

        if capital <= 0:
            return {
                "phase": "neutral",
                "risk_pct": 0.0,
                "stake_value": 0.0,
                "score_shift": 0.0,
                "confidence_shift": 0,
                "reason": "Capital Mind neutro (sem capital informado)",
                "target_value": 0.0,
                "stop_value": 0.0,
            }

        if confidence >= 85 and adjusted_score >= 3.2:
            risk_pct = 0.020
        elif confidence >= 75 and adjusted_score >= 2.6:
            risk_pct = 0.015
        elif confidence >= 65 and adjusted_score >= 1.9:
            risk_pct = 0.010
        else:
            risk_pct = 0.006

        score_shift = 0.0
        confidence_shift = 0
        reason = "Capital Mind neutro"

        if phase == "defensive":
            risk_pct *= 0.60
            score_shift -= 0.08
            confidence_shift -= 3
            reason = "Capital Mind defensivo"
        elif phase == "expansion":
            risk_pct *= 1.12
            score_shift += 0.05
            confidence_shift += 2
            reason = "Capital Mind em expansão"

        if streak <= -3:
            risk_pct *= 0.70
            score_shift -= 0.05
            confidence_shift -= 2
            reason += " • reduzindo após sequência negativa"
        elif streak >= 3:
            risk_pct *= 1.08
            confidence_shift += 1
            reason += " • reforçando consistência recente"

        risk_pct = max(0.0035, min(0.025, risk_pct))

        target_value = capital * (daily_target_pct / 100.0)
        stop_value = capital * (daily_stop_pct / 100.0)

        if daily_pnl >= target_value and target_value > 0:
            score_shift -= 0.10
            confidence_shift -= 2
            risk_pct *= 0.70
            reason += " • preservando meta do dia"

        if daily_pnl <= -stop_value and stop_value > 0:
            score_shift -= 0.20
            confidence_shift -= 5
            risk_pct *= 0.40
            reason += " • proteção de capital"

        stake_value = round(capital * risk_pct, 2)

        return {
            "phase": phase,
            "risk_pct": round(risk_pct * 100, 2),
            "stake_value": stake_value,
            "score_shift": round(score_shift, 2),
            "confidence_shift": int(confidence_shift),
            "reason": reason,
            "target_value": round(target_value, 2),
            "stop_value": round(stop_value, 2),
        }
