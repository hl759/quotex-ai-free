import json
import math
import os
import time
from copy import deepcopy
from statistics import mean

from storage_paths import DATA_DIR, migrate_file
from json_safe import safe_dump
from state_store import get_state_store

OPTIMIZER_FILE = os.path.join(DATA_DIR, "alpha_hive_self_optimizer.json")
migrate_file(OPTIMIZER_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_self_optimizer.json")])
STORE_KEY = "self_optimization_store"


class SelfOptimizationEngine:
    """
    Camada de auto-otimização conservadora.

    Não reescreve a lógica central. Apenas observa resultados, mantém um journal
    unificado dos dois modos e devolve ajustes graduais quando existe amostra
    estatisticamente útil.
    """

    MODES = ("BINARY_MODE", "FUTURES_MODE")

    def __init__(self):
        self.store = get_state_store()
        self.state = self._load()

    def _default_state(self):
        return {
            "active_mode": "BINARY_MODE",
            "trades": [],
            "open_futures": {},
            "last_updated_ts": 0,
            "version": 1,
        }

    def _load(self):
        store_value = self.store.get_json(STORE_KEY, None)
        if isinstance(store_value, dict) and store_value:
            data = store_value
        elif os.path.exists(OPTIMIZER_FILE):
            try:
                with open(OPTIMIZER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = self._default_state()
        else:
            data = self._default_state()

        if not isinstance(data, dict):
            data = self._default_state()

        for key, value in self._default_state().items():
            data.setdefault(key, deepcopy(value))
        if not isinstance(data.get("trades"), list):
            data["trades"] = []
        if not isinstance(data.get("open_futures"), dict):
            data["open_futures"] = {}
        if str(data.get("active_mode", "BINARY_MODE")) not in self.MODES:
            data["active_mode"] = "BINARY_MODE"
        return data

    def _save(self):
        self.state["last_updated_ts"] = int(time.time())
        self.store.set_json(STORE_KEY, self.state)
        tmp = OPTIMIZER_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(self.state, f)
        os.replace(tmp, OPTIMIZER_FILE)

    def get_active_mode(self):
        mode = str(self.state.get("active_mode", "BINARY_MODE"))
        return mode if mode in self.MODES else "BINARY_MODE"

    def set_active_mode(self, mode):
        normalized = str(mode or "BINARY_MODE").upper().strip()
        if normalized not in self.MODES:
            raise ValueError("unsupported_mode")
        self.state["active_mode"] = normalized
        self._save()
        return normalized

    def _safe_float(self, value, default=0.0):
        try:
            if value is None or value == "":
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def _safe_int(self, value, default=0):
        try:
            if value is None or value == "":
                return int(default)
            return int(float(value))
        except Exception:
            return int(default)

    def _trade_uid(self, trade):
        uid = str(trade.get("uid") or "").strip()
        if uid:
            return uid
        parts = [
            trade.get("mode", "UNKNOWN"),
            trade.get("asset", "N/A"),
            trade.get("setup_type", "none"),
            trade.get("analysis_time", "--:--"),
            str(trade.get("direction") or trade.get("signal") or "NONE"),
        ]
        return "|".join(str(p) for p in parts)

    def _hour_bucket(self, hhmm):
        try:
            text = str(hhmm or "").strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            if 0 <= hour <= 23:
                return f"{hour:02d}:00"
        except Exception:
            pass
        return "unknown"

    def _recent_trades(self, mode=None, limit=None):
        rows = list(self.state.get("trades", []))
        if mode:
            rows = [t for t in rows if str(t.get("mode")) == str(mode)]
        if limit:
            rows = rows[: max(1, int(limit))]
        return rows

    def _result_to_win(self, result):
        text = str(result or "").upper()
        if text == "WIN":
            return 1
        if text == "LOSS":
            return 0
        return None

    def _append_trade(self, trade):
        if not isinstance(trade, dict):
            return None
        trade = deepcopy(trade)
        trade.setdefault("uid", self._trade_uid(trade))
        trades = [t for t in self.state.get("trades", []) if self._trade_uid(t) != trade["uid"]]
        trades.insert(0, trade)
        self.state["trades"] = trades[:5000]
        self._save()
        return trade

    def _calc_drawdown_pct(self, mode):
        curve = 0.0
        peak = 0.0
        max_dd = 0.0
        for trade in reversed(self._recent_trades(mode=mode)):
            curve += self._safe_float(trade.get("pnl"), 0.0)
            peak = max(peak, curve)
            if peak > 0:
                dd = ((peak - curve) / peak) * 100.0
                max_dd = max(max_dd, dd)
            elif curve < 0:
                max_dd = max(max_dd, abs(curve) * 100.0)
        return round(max_dd, 2)

    def _consecutive_losses(self, mode, limit=12):
        streak = 0
        for trade in self._recent_trades(mode=mode, limit=limit):
            outcome = str(trade.get("result", "")).upper()
            if outcome == "LOSS":
                streak += 1
            elif outcome == "WIN":
                break
        return streak

    def _daily_pnl(self, mode, date_text=None):
        if not date_text:
            date_text = time.strftime("%Y-%m-%d")
        total = 0.0
        for trade in self._recent_trades(mode=mode):
            if str(trade.get("date") or "") == str(date_text):
                total += self._safe_float(trade.get("pnl"), 0.0)
        return round(total, 2)

    def _aggregate(self, rows):
        valid = [r for r in rows if str(r.get("result", "")).upper() in ("WIN", "LOSS")]
        total = len(valid)
        wins = sum(1 for r in valid if str(r.get("result", "")).upper() == "WIN")
        losses = total - wins
        pnls = [self._safe_float(r.get("pnl"), 0.0) for r in valid]
        rs = [self._safe_float(r.get("r_multiple"), 0.0) for r in valid]
        gross_profit = sum(x for x in pnls if x > 0)
        gross_loss = abs(sum(x for x in pnls if x < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "winrate": round((wins / total) * 100.0, 2) if total else 0.0,
            "expectancy_r": round(mean(rs), 4) if rs else 0.0,
            "avg_pnl": round(mean(pnls), 4) if pnls else 0.0,
            "profit_factor": round(profit_factor, 3),
            "total_pnl": round(sum(pnls), 4),
        }

    def _match_rows(self, mode, asset=None, setup_type=None, market_condition=None, hour_bucket=None):
        rows = self._recent_trades(mode=mode)
        if asset:
            rows = [r for r in rows if str(r.get("asset")) == str(asset)]
        if setup_type:
            rows = [r for r in rows if str(r.get("setup_type")) == str(setup_type)]
        if market_condition:
            rows = [r for r in rows if str(r.get("market_condition")) == str(market_condition)]
        if hour_bucket:
            rows = [r for r in rows if str(r.get("time_bucket")) == str(hour_bucket)]
        return rows

    def _weighted_segment_score(self, overall_stats, segment_stats, recent_stats):
        # Score conservador: mistura longo prazo, segmento específico e janela recente.
        base = 0.0
        for weight, stats in ((0.35, overall_stats), (0.40, segment_stats), (0.25, recent_stats)):
            total = stats.get("total", 0)
            if total <= 0:
                continue
            win_component = ((stats.get("winrate", 50.0) - 50.0) / 50.0) * 0.8
            expectancy_component = stats.get("expectancy_r", 0.0) * 0.9
            pf = stats.get("profit_factor", 1.0)
            pf_component = max(-0.5, min(0.5, (pf - 1.0) * 0.35))
            sample_component = min(1.0, total / 80.0)
            base += weight * (win_component + expectancy_component + pf_component) * sample_component
        return round(base, 4)

    def register_binary_outcome(self, signal, result_data):
        outcome = str(result_data.get("result", "")).upper()
        if outcome not in ("WIN", "LOSS"):
            return None
        trade = {
            "uid": signal.get("uid"),
            "mode": "BINARY_MODE",
            "asset": signal.get("asset"),
            "setup_type": signal.get("strategy_name", "binary_core"),
            "market_condition": signal.get("environment_type", signal.get("regime", "unknown")),
            "time_bucket": self._hour_bucket(signal.get("analysis_session", signal.get("analysis_time"))),
            "analysis_time": signal.get("analysis_time"),
            "date": signal.get("date"),
            "direction": signal.get("signal"),
            "confidence": self._safe_int(signal.get("confidence"), 50),
            "entry_quality": round(self._safe_float(signal.get("score"), 0.0), 4),
            "exit_efficiency": round(self._safe_float(result_data.get("gross_r"), 0.0), 4),
            "drawdown_pct": 0.0,
            "leverage": 1.0,
            "pnl": round(self._safe_float(result_data.get("gross_pnl"), 0.0), 4),
            "r_multiple": round(self._safe_float(result_data.get("gross_r"), 0.0), 4),
            "result": outcome,
        }
        return self._append_trade(trade)

    def register_futures_plan(self, plan):
        if not isinstance(plan, dict):
            return None
        uid = self._trade_uid({
            "uid": plan.get("uid"),
            "mode": "FUTURES_MODE",
            "asset": plan.get("asset"),
            "setup_type": plan.get("setup_type", "futures_confluence"),
            "analysis_time": plan.get("analysis_time"),
            "direction": plan.get("direction"),
        })
        stored = deepcopy(plan)
        stored["uid"] = uid
        self.state.setdefault("open_futures", {})[uid] = stored
        self._save()
        return uid

    def register_futures_close(self, close_report):
        if not isinstance(close_report, dict):
            return None
        uid = str(close_report.get("uid") or "").strip()
        if not uid:
            uid = self._trade_uid({
                "mode": "FUTURES_MODE",
                "asset": close_report.get("asset"),
                "setup_type": close_report.get("setup_type", "futures_confluence"),
                "analysis_time": close_report.get("analysis_time"),
                "direction": close_report.get("direction"),
            })
        base = deepcopy(self.state.get("open_futures", {}).get(uid, {}))
        merged = {**base, **close_report}
        result = str(merged.get("result", "")).upper()
        if result not in ("WIN", "LOSS"):
            realized_pnl = self._safe_float(merged.get("realized_pnl"), 0.0)
            result = "WIN" if realized_pnl > 0 else "LOSS"
        risk_amount = abs(self._safe_float(merged.get("risk_amount"), 0.0))
        realized_pnl = self._safe_float(merged.get("realized_pnl"), merged.get("pnl"))
        r_multiple = self._safe_float(merged.get("r_multiple"), 0.0)
        if abs(r_multiple) < 1e-9 and risk_amount > 0:
            r_multiple = realized_pnl / risk_amount
        trade = {
            "uid": uid,
            "mode": "FUTURES_MODE",
            "asset": merged.get("asset"),
            "setup_type": merged.get("setup_type", "futures_confluence"),
            "market_condition": merged.get("market_condition", merged.get("regime", "unknown")),
            "time_bucket": merged.get("time_bucket") or self._hour_bucket(merged.get("analysis_time")),
            "analysis_time": merged.get("analysis_time"),
            "date": merged.get("date") or time.strftime("%Y-%m-%d"),
            "direction": merged.get("direction"),
            "confidence": self._safe_int(merged.get("confidence"), 50),
            "entry_quality": round(self._safe_float(merged.get("confluence_score"), merged.get("entry_quality")), 4),
            "exit_efficiency": round(self._safe_float(merged.get("exit_efficiency"), r_multiple), 4),
            "drawdown_pct": round(self._safe_float(merged.get("drawdown_pct"), 0.0), 4),
            "leverage": round(self._safe_float(merged.get("leverage"), 1.0), 4),
            "pnl": round(realized_pnl, 4),
            "r_multiple": round(r_multiple, 4),
            "result": result,
        }
        self.state.setdefault("open_futures", {}).pop(uid, None)
        return self._append_trade(trade)

    def build_mode_summary(self, mode):
        rows = self._recent_trades(mode=mode)
        overall = self._aggregate(rows)
        recent = self._aggregate(rows[:20])
        return {
            **overall,
            "recent": recent,
            "drawdown_pct": self._calc_drawdown_pct(mode),
            "consecutive_losses": self._consecutive_losses(mode),
            "daily_pnl": self._daily_pnl(mode),
            "open_positions": len(self.state.get("open_futures", {})) if mode == "FUTURES_MODE" else 0,
        }

    def get_mode_adjustments(self, mode, asset=None, setup_type=None, market_condition=None, analysis_time=None, capital_state=None):
        mode = str(mode or "BINARY_MODE")
        time_bucket = self._hour_bucket(analysis_time)
        overall_rows = self._recent_trades(mode=mode)
        segment_rows = self._match_rows(mode, asset=asset, setup_type=setup_type, market_condition=market_condition, hour_bucket=time_bucket)
        recent_rows = overall_rows[:20]

        overall_stats = self._aggregate(overall_rows)
        segment_stats = self._aggregate(segment_rows)
        recent_stats = self._aggregate(recent_rows)

        score = self._weighted_segment_score(overall_stats, segment_stats, recent_stats)
        mode_summary = self.build_mode_summary(mode)
        drawdown_pct = mode_summary.get("drawdown_pct", 0.0)
        consecutive_losses = mode_summary.get("consecutive_losses", 0)

        min_sample = 18 if mode == "BINARY_MODE" else 12
        strong_sample = 45 if mode == "BINARY_MODE" else 28
        total_segment = segment_stats.get("total", 0)
        total_overall = overall_stats.get("total", 0)

        confidence_floor = 64 if mode == "BINARY_MODE" else 62
        score_multiplier = 1.0
        risk_multiplier = 1.0
        leverage_multiplier = 1.0
        frequency_limit = 1
        allow_trade = True
        cooldown_minutes = 0
        reasons = []

        if total_overall < min_sample:
            reasons.append("Self-Optimization: amostra global insuficiente, operando neutro")
            return {
                "mode": mode,
                "score": 0.0,
                "confidence_floor": confidence_floor,
                "score_multiplier": score_multiplier,
                "risk_multiplier": risk_multiplier,
                "leverage_multiplier": leverage_multiplier,
                "frequency_limit": frequency_limit,
                "allow_trade": allow_trade,
                "cooldown_minutes": cooldown_minutes,
                "segment_sample": total_segment,
                "overall_sample": total_overall,
                "reasons": reasons,
            }

        if score >= 0.18 and total_segment >= min_sample:
            confidence_floor -= 2
            score_multiplier = 0.97
            risk_multiplier = 1.08 if mode == "FUTURES_MODE" else 1.02
            leverage_multiplier = 1.08 if mode == "FUTURES_MODE" else 1.0
            frequency_limit = 2 if total_segment >= strong_sample else 1
            reasons.append("Self-Optimization: segmento forte liberou pequena expansão")
        elif score <= -0.12:
            confidence_floor += 4
            score_multiplier = 1.05
            risk_multiplier = 0.82
            leverage_multiplier = 0.84
            frequency_limit = 1
            reasons.append("Self-Optimization: segmento fraco pediu defesa")

        if total_segment >= strong_sample and segment_stats.get("winrate", 0.0) >= 61 and segment_stats.get("expectancy_r", 0.0) > 0.08:
            confidence_floor = max(58, confidence_floor - 2)
            risk_multiplier = min(1.12, risk_multiplier * 1.03)
            reasons.append("Self-Optimization: consistência forte confirmada")
        elif total_segment >= strong_sample and segment_stats.get("winrate", 0.0) <= 45:
            confidence_floor = min(76, confidence_floor + 3)
            leverage_multiplier *= 0.90
            reasons.append("Self-Optimization: consistência fraca endureceu filtros")

        if consecutive_losses >= 3:
            risk_multiplier *= 0.65
            leverage_multiplier *= 0.72
            confidence_floor += 3
            cooldown_minutes = 30 if mode == "FUTURES_MODE" else 20
            reasons.append("Self-Optimization: sequência de perdas ativou resfriamento")

        if drawdown_pct >= 7.5:
            risk_multiplier *= 0.50
            leverage_multiplier *= 0.65
            confidence_floor += 5
            frequency_limit = 0
            allow_trade = False
            cooldown_minutes = max(cooldown_minutes, 60)
            reasons.append("Self-Optimization: drawdown crítico bloqueou novas entradas")
        elif drawdown_pct >= 4.0:
            risk_multiplier *= 0.72
            leverage_multiplier *= 0.80
            confidence_floor += 3
            reasons.append("Self-Optimization: drawdown moderado reduziu agressividade")

        capital_current = self._safe_float((capital_state or {}).get("capital_current"), 0.0)
        capital_peak = self._safe_float((capital_state or {}).get("capital_peak"), capital_current)
        if capital_peak > 0 and capital_current > 0:
            current_dd = ((capital_peak - capital_current) / capital_peak) * 100.0
            if current_dd >= 6.0:
                risk_multiplier *= 0.55
                leverage_multiplier *= 0.70
                confidence_floor += 4
                reasons.append("Self-Optimization: drawdown do capital reduziu risco")

        return {
            "mode": mode,
            "score": round(score, 4),
            "confidence_floor": int(max(55, min(84, confidence_floor))),
            "score_multiplier": round(max(0.90, min(1.08, score_multiplier)), 4),
            "risk_multiplier": round(max(0.35, min(1.15, risk_multiplier)), 4),
            "leverage_multiplier": round(max(0.35, min(1.15, leverage_multiplier)), 4),
            "frequency_limit": int(max(0, min(3, frequency_limit))),
            "allow_trade": bool(allow_trade),
            "cooldown_minutes": int(max(0, cooldown_minutes)),
            "segment_sample": total_segment,
            "overall_sample": total_overall,
            "reasons": reasons,
        }

    def risk_profile(self, mode, capital_state=None):
        capital_state = capital_state or {}
        adjustment = self.get_mode_adjustments(mode=mode, capital_state=capital_state)
        if mode == "FUTURES_MODE":
            base_risk = 0.0065
            max_trades_per_hour = 3
            max_daily_loss_pct = 2.8
        else:
            base_risk = 0.005
            max_trades_per_hour = 4
            max_daily_loss_pct = 2.2

        risk_pct = base_risk * adjustment.get("risk_multiplier", 1.0)
        risk_pct = max(0.0025, min(0.012, risk_pct))

        daily_pnl = self._daily_pnl(mode)
        capital_current = self._safe_float(capital_state.get("capital_current"), 0.0)
        daily_loss_pct = abs(daily_pnl) / capital_current * 100.0 if capital_current > 0 and daily_pnl < 0 else 0.0
        allow_trade = adjustment.get("allow_trade", True) and daily_loss_pct < max_daily_loss_pct
        return {
            "mode": mode,
            "risk_pct": round(risk_pct, 4),
            "max_trades_per_hour": max(1, min(5, adjustment.get("frequency_limit", 1) + max_trades_per_hour - 1)),
            "max_daily_loss_pct": max_daily_loss_pct,
            "allow_trade": bool(allow_trade),
            "cooldown_minutes": adjustment.get("cooldown_minutes", 0),
            "reasons": list(adjustment.get("reasons", [])),
        }

    def summary(self):
        return {
            "active_mode": self.get_active_mode(),
            "binary": self.build_mode_summary("BINARY_MODE"),
            "futures": self.build_mode_summary("FUTURES_MODE"),
            "open_futures": len(self.state.get("open_futures", {})),
            "tracked_trades": len(self.state.get("trades", [])),
        }
