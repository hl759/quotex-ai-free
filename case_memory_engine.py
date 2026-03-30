import json
import os
from storage_paths import DATA_DIR, migrate_file

from config import DEFAULT_PAYOUT
from trader_genome import asset_class_for, parse_session_bucket

os.makedirs(DATA_DIR, exist_ok=True)
LEDGER_FILE = os.path.join(DATA_DIR, "alpha_hive_trade_ledger.json")
migrate_file(LEDGER_FILE, [os.path.join("/opt/render/project/src/data", "alpha_hive_trade_ledger.json")])


class CaseMemoryEngine:
    def __init__(self):
        self.ledger_file = LEDGER_FILE

    def _load_ledger(self):
        try:
            if os.path.exists(self.ledger_file):
                with open(self.ledger_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
        except Exception:
            pass
        return []

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _hour_bucket(self, indicators):
        return parse_session_bucket(indicators.get("analysis_time"))

    def _similarity(self, trade, asset, indicators, strategy_name, direction):
        score = 0.0
        if str(trade.get("asset")) == str(asset):
            score += 4.0
        elif asset_class_for(trade.get("asset")) == asset_class_for(asset):
            score += 1.4

        if str(trade.get("regime", "unknown")) == str(indicators.get("regime", "unknown")):
            score += 2.8
        if str(trade.get("strategy_name", "none")) == str(strategy_name):
            score += 2.6
        elif str(trade.get("strategy_name", "")).split("_")[0] == str(strategy_name).split("_")[0]:
            score += 1.4
        if str(trade.get("signal", "")).upper() == str(direction).upper():
            score += 1.6
        if str(trade.get("environment_type", "unknown")) == str(indicators.get("environment_type", "unknown")):
            score += 1.0
        trade_session = trade.get("analysis_session") or parse_session_bucket(trade.get("analysis_time"))
        if str(trade_session or "unknown") == str(self._hour_bucket(indicators)):
            score += 1.0
        for key, weight in {
            "breakout": 0.8,
            "rejection": 0.8,
            "volatility": 0.7,
            "moved_too_fast": 0.6,
            "is_sideways": 0.7,
            "pattern": 0.6,
            "trend_m1": 0.8,
            "trend_m5": 0.8,
            "market_narrative": 0.8,
            "breakout_quality": 0.7,
            "conflict_type": 0.8,
        }.items():
            incoming = indicators.get(key)
            seen = trade.get(key)
            if incoming is not None and seen is not None and str(incoming) == str(seen):
                score += weight
        return score

    def lookup(self, asset, indicators, strategy_name, direction, limit=80):
        ledger = [t for t in self._load_ledger() if str(t.get("result", "")).upper() in ("WIN", "LOSS")]
        if not ledger:
            return {
                "similar_cases": [],
                "summary": {
                    "total": 0,
                    "wins": 0,
                    "losses": 0,
                    "winrate": 0.0,
                    "expectancy_r": 0.0,
                    "avg_payout": round(DEFAULT_PAYOUT, 4),
                    "breakeven_winrate": round((1 / (1 + DEFAULT_PAYOUT)) * 100.0, 2),
                },
                "scar_tissue": ["Sem memória histórica suficiente"],
            }

        ranked = []
        for trade in ledger:
            sim = self._similarity(trade, asset, indicators, strategy_name, direction)
            if sim >= 4.5:
                ranked.append((sim, trade))
        ranked.sort(key=lambda x: x[0], reverse=True)
        selected = [t for _, t in ranked[: max(5, int(limit or 80))]]

        wins = sum(1 for t in selected if str(t.get("result", "")).upper() == "WIN")
        losses = sum(1 for t in selected if str(t.get("result", "")).upper() == "LOSS")
        total = len(selected)
        rs = [self._safe_float(t.get("gross_r"), 0.0) for t in selected]
        payouts = [max(0.0, self._safe_float(t.get("payout"), DEFAULT_PAYOUT)) for t in selected]
        avg_payout = sum(payouts) / len(payouts) if payouts else DEFAULT_PAYOUT
        breakeven = round((1 / (1 + avg_payout)) * 100.0, 2) if avg_payout > 0 else 100.0
        expectancy_r = round(sum(rs) / len(rs), 4) if rs else 0.0
        winrate = round((wins / total) * 100.0, 2) if total else 0.0

        scar_tissue = []
        if total >= 8 and expectancy_r < 0:
            scar_tissue.append("Casos muito parecidos carregam expectativa negativa")
        if total >= 8 and winrate < breakeven:
            scar_tissue.append("Memória de casos mostra winrate abaixo do break-even")
        if total >= 10:
            same_hour = [t for t in selected if str((t.get("analysis_session") or parse_session_bucket(t.get("analysis_time"))) or "unknown") == str(self._hour_bucket(indicators))]
            if same_hour:
                same_hour_wr = round((sum(1 for t in same_hour if str(t.get("result", "")).upper() == "WIN") / len(same_hour)) * 100.0, 2)
                if same_hour_wr < breakeven:
                    scar_tissue.append("Mesmo horário aparece como zona de cicatriz")
        if indicators.get("moved_too_fast"):
            fast = [t for t in selected if bool(t.get("moved_too_fast", False))]
            if len(fast) >= 6:
                fast_wr = round((sum(1 for t in fast if str(t.get("result", "")).upper() == "WIN") / len(fast)) * 100.0, 2)
                if fast_wr < breakeven:
                    scar_tissue.append("Preço já esticado costuma machucar contextos parecidos")

        if not scar_tissue:
            scar_tissue.append("Memória de casos não encontrou trauma dominante")

        compact = []
        for trade in selected[:10]:
            compact.append({
                "asset": trade.get("asset"),
                "strategy_name": trade.get("strategy_name"),
                "regime": trade.get("regime"),
                "signal": trade.get("signal"),
                "result": trade.get("result"),
                "gross_r": trade.get("gross_r"),
                "analysis_time": trade.get("analysis_time"),
            })

        return {
            "similar_cases": compact,
            "summary": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "winrate": winrate,
                "expectancy_r": expectancy_r,
                "avg_payout": round(avg_payout, 4),
                "breakeven_winrate": breakeven,
            },
            "scar_tissue": scar_tissue,
        }
