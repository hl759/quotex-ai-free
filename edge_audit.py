import json
import math
import os
from statistics import mean

from config import DEFAULT_PAYOUT, EDGE_PROOF_MIN_TRADES, EDGE_SEGMENT_MIN_TRADES

DATA_DIR = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
os.makedirs(DATA_DIR, exist_ok=True)

LEDGER_FILE = os.path.join(DATA_DIR, "alpha_hive_trade_ledger.json")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "alpha_hive_edge_snapshot.json")


class EdgeAuditEngine:
    def __init__(self):
        self.ledger_file = LEDGER_FILE
        self.snapshot_file = SNAPSHOT_FILE

    def _load_json(self, path, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, type(default)) else default
        except Exception:
            pass
        return default

    def _save_json(self, path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _result_value(self, trade):
        return str(trade.get("result", "")).upper()

    def _hour_bucket(self, trade):
        try:
            text = str(trade.get("analysis_time", "")).strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def _trade_uid(self, signal, result_data):
        explicit = signal.get("uid") or result_data.get("uid")
        if explicit:
            return str(explicit)
        return "-".join([
            str(signal.get("asset", "N/A")),
            str(signal.get("signal", "N/A")),
            str(signal.get("analysis_time", "--:--")),
            str(signal.get("entry_time", "--:--")),
            str(signal.get("expiration", "--:--")),
        ])

    def _normalized_trade(self, signal, result_data):
        payout = max(0.0, self._safe_float(result_data.get("payout", signal.get("payout", DEFAULT_PAYOUT)), DEFAULT_PAYOUT))
        stake = max(0.0, self._safe_float(result_data.get("stake", signal.get("stake_value", signal.get("suggested_stake", signal.get("stake", 0.0)))), 0.0))
        gross_pnl = self._safe_float(result_data.get("gross_pnl"), 0.0)
        gross_r = self._safe_float(result_data.get("gross_r"), 0.0)
        breakeven_winrate = self._safe_float(result_data.get("breakeven_winrate"), 0.0)
        trade = {
            "uid": self._trade_uid(signal, result_data),
            "date": signal.get("date"),
            "asset": signal.get("asset"),
            "signal": str(signal.get("signal", "")).upper(),
            "strategy_name": signal.get("strategy_name", "none"),
            "regime": signal.get("regime", "unknown"),
            "analysis_time": signal.get("analysis_time"),
            "entry_time": signal.get("entry_time"),
            "expiration": signal.get("expiration"),
            "score": self._safe_float(signal.get("score"), 0.0),
            "confidence": int(self._safe_float(signal.get("confidence"), 0)),
            "setup_id": signal.get("setup_id"),
            "context_id": signal.get("context_id"),
            "evolution_variant": signal.get("evolution_variant", "base"),
            "risk_pct": self._safe_float(signal.get("risk_pct"), 0.0),
            "stake": round(stake, 2),
            "payout": round(payout, 4),
            "result": self._result_value(result_data),
            "win": bool(result_data.get("win", False)),
            "entry_price": result_data.get("entry_price"),
            "exit_price": result_data.get("exit_price"),
            "entry_candle_time": result_data.get("entry_candle_time"),
            "exit_candle_time": result_data.get("exit_candle_time"),
            "evaluation_mode": result_data.get("evaluation_mode", "candle_close"),
            "execution_delay_candles": int(self._safe_float(result_data.get("execution_delay_candles"), 0)),
            "gross_pnl": round(gross_pnl, 2),
            "gross_r": round(gross_r, 4),
            "breakeven_winrate": round(breakeven_winrate, 2),
        }
        return trade

    def _load_ledger(self):
        return self._load_json(self.ledger_file, [])

    def record_trade(self, signal, result_data):
        if not isinstance(signal, dict) or not isinstance(result_data, dict):
            return None
        trade = self._normalized_trade(signal, result_data)
        ledger = self._load_ledger()
        existing = {str(item.get("uid")) for item in ledger if isinstance(item, dict)}
        if trade["uid"] in existing:
            return trade
        ledger.insert(0, trade)
        if len(ledger) > 10000:
            ledger = ledger[:10000]
        self._save_json(self.ledger_file, ledger)
        snapshot = self.compute_report(ledger)
        self._save_json(self.snapshot_file, snapshot)
        return trade

    def _valid(self, trades):
        return [t for t in trades if self._result_value(t) in ("WIN", "LOSS")]

    def _breakeven_for(self, payout):
        payout = max(0.0, self._safe_float(payout, DEFAULT_PAYOUT))
        if payout <= 0:
            return 100.0
        return round((1.0 / (1.0 + payout)) * 100.0, 2)

    def _drawdown(self, trades):
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for trade in reversed(trades):
            equity += self._safe_float(trade.get("gross_pnl"), 0.0)
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return round(max_dd, 2)

    def _segment_stats(self, trades, key):
        groups = {}
        for trade in trades:
            if key == "hour":
                bucket = self._hour_bucket(trade)
            else:
                bucket = str(trade.get(key, "unknown") or "unknown")
            groups.setdefault(bucket, []).append(trade)
        rows = []
        for bucket, rows_trades in groups.items():
            stats = self._summary(rows_trades)
            stats[key] = bucket
            rows.append(stats)
        rows = [r for r in rows if r.get("total", 0) >= EDGE_SEGMENT_MIN_TRADES]
        rows.sort(key=lambda x: (x.get("expectancy_r", 0.0), x.get("profit_factor", 0.0), x.get("total", 0)), reverse=True)
        return rows

    def _status(self, stats):
        total = int(stats.get("total", 0))
        expectancy = self._safe_float(stats.get("expectancy_r"), 0.0)
        pf = self._safe_float(stats.get("profit_factor"), 0.0)
        wr = self._safe_float(stats.get("winrate", 0.0), 0.0)
        be = self._safe_float(stats.get("breakeven_winrate", 100.0), 100.0)
        if total < max(30, EDGE_SEGMENT_MIN_TRADES):
            return "amostra_insuficiente"
        if total < EDGE_PROOF_MIN_TRADES:
            return "em_validacao" if expectancy > 0 and pf > 1.0 and wr > be else "frágil"
        if expectancy > 0 and pf >= 1.15 and wr > be:
            return "edge_positivo"
        return "nao_comprovado"

    def _summary(self, trades):
        valid = self._valid(trades)
        if not valid:
            return {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "winrate": 0.0,
                "avg_payout": round(DEFAULT_PAYOUT, 4),
                "breakeven_winrate": self._breakeven_for(DEFAULT_PAYOUT),
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "expectancy_r": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
            }
        wins = sum(1 for t in valid if self._result_value(t) == "WIN")
        losses = sum(1 for t in valid if self._result_value(t) == "LOSS")
        total = len(valid)
        payouts = [max(0.0, self._safe_float(t.get("payout"), DEFAULT_PAYOUT)) for t in valid]
        pnls = [self._safe_float(t.get("gross_pnl"), 0.0) for t in valid]
        rs = [self._safe_float(t.get("gross_r"), 0.0) for t in valid]
        avg_payout = mean(payouts) if payouts else DEFAULT_PAYOUT
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        stats = {
            "total": total,
            "wins": wins,
            "losses": losses,
            "winrate": round((wins / total) * 100.0, 2) if total else 0.0,
            "avg_payout": round(avg_payout, 4),
            "breakeven_winrate": self._breakeven_for(avg_payout),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(mean(pnls), 4) if pnls else 0.0,
            "expectancy_r": round(mean(rs), 4) if rs else 0.0,
            "profit_factor": round(profit_factor, 3),
            "max_drawdown": self._drawdown(valid),
        }
        stats["status"] = self._status(stats)
        return stats

    def compute_report(self, trades=None):
        ledger = trades if isinstance(trades, list) else self._load_ledger()
        valid = self._valid(ledger)
        summary = self._summary(valid)
        assets = self._segment_stats(valid, "asset")
        regimes = self._segment_stats(valid, "regime")
        strategies = self._segment_stats(valid, "strategy_name")
        hours = self._segment_stats(valid, "hour")
        return {
            "summary": summary,
            "top_assets": assets[:5],
            "weak_assets": list(reversed(assets[-5:])) if assets else [],
            "top_regimes": regimes[:5],
            "top_strategies": strategies[:5],
            "top_hours": hours[:5],
        }
