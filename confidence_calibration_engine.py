import math
import time
from collections import defaultdict

from config import CALIBRATION_MIN_BUCKET_TRADES, CALIBRATION_SHRINKAGE, DEFAULT_PAYOUT
from state_store import get_state_store

COLLECTION_NAME = "journal_trades"


class ConfidenceCalibrationEngine:
    def __init__(self, cache_ttl=45, max_rows=2500):
        self.store = get_state_store()
        self.cache_ttl = max(5, int(cache_ttl or 45))
        self.max_rows = max(200, int(max_rows or 2500))
        self._cached_rows = None
        self._cached_at = 0.0

    def _strategy_family(self, name):
        text = str(name or "none")
        if text.startswith("trend"):
            return "trend"
        if text.startswith("reversal"):
            return "reversal"
        if text.startswith("scalp"):
            return "scalp"
        return text.split("_")[0]

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _bucket(self, confidence):
        val = int(round(self._safe_float(confidence, 50.0)))
        val = max(50, min(95, val))
        return int(math.floor(val / 5.0) * 5)

    def _load_rows(self):
        now = time.time()
        if self._cached_rows is not None and (now - self._cached_at) <= self.cache_ttl:
            return self._cached_rows
        rows = self.store.list_collection(COLLECTION_NAME, limit=self.max_rows) or []
        valid = []
        for row in rows:
            result = str(row.get("result", "")).upper()
            if result not in ("WIN", "LOSS"):
                continue
            row = dict(row)
            row["confidence_bucket"] = self._bucket(row.get("confidence", 50))
            row["strategy_family"] = self._strategy_family(row.get("strategy_name"))
            valid.append(row)
        self._cached_rows = valid
        self._cached_at = now
        return valid

    def _summary(self, rows):
        total = len(rows)
        wins = sum(1 for r in rows if str(r.get("result", "")).upper() == "WIN")
        losses = total - wins
        if total <= 0:
            return {"total": 0, "wins": 0, "losses": 0, "winrate": 0.0}
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "winrate": (wins / total) * 100.0,
        }

    def estimate(self, confidence, asset=None, regime=None, strategy_name=None, environment_type=None, payout=None):
        rows = self._load_rows()
        prob_from_model = max(0.01, min(0.99, self._safe_float(confidence, 50.0) / 100.0))
        payout = max(0.0, self._safe_float(payout, DEFAULT_PAYOUT))
        breakeven = (1.0 / (1.0 + payout)) if payout > 0 else 1.0
        if not rows:
            expectancy = prob_from_model * payout - (1.0 - prob_from_model)
            return {
                "probability": round(prob_from_model, 4),
                "raw_probability": round(prob_from_model, 4),
                "source": "model_only",
                "sample": 0,
                "breakeven_probability": round(breakeven, 4),
                "expectancy_r": round(expectancy, 4),
                "bucket": self._bucket(confidence),
            }

        bucket = self._bucket(confidence)
        family = self._strategy_family(strategy_name)
        global_stats = self._summary(rows)
        global_prob = (global_stats["wins"] + 2.0) / (global_stats["total"] + 4.0) if global_stats["total"] > 0 else prob_from_model

        candidate_filters = [
            ("bucket_asset_regime_family_env", lambda r: r.get("confidence_bucket") == bucket and r.get("asset") == asset and r.get("regime") == regime and r.get("strategy_family") == family and r.get("environment_type") == environment_type),
            ("bucket_regime_family_env", lambda r: r.get("confidence_bucket") == bucket and r.get("regime") == regime and r.get("strategy_family") == family and r.get("environment_type") == environment_type),
            ("bucket_family_env", lambda r: r.get("confidence_bucket") == bucket and r.get("strategy_family") == family and r.get("environment_type") == environment_type),
            ("bucket_regime", lambda r: r.get("confidence_bucket") == bucket and r.get("regime") == regime),
            ("bucket_env", lambda r: r.get("confidence_bucket") == bucket and r.get("environment_type") == environment_type),
            ("bucket_family", lambda r: r.get("confidence_bucket") == bucket and r.get("strategy_family") == family),
            ("bucket_only", lambda r: r.get("confidence_bucket") == bucket),
        ]

        chosen_name = "global"
        chosen_rows = rows
        for name, predicate in candidate_filters:
            subset = [r for r in rows if predicate(r)]
            if len(subset) >= CALIBRATION_MIN_BUCKET_TRADES:
                chosen_name = name
                chosen_rows = subset
                break

        stats = self._summary(chosen_rows)
        local_prob = (stats["wins"] + 1.0) / (stats["total"] + 2.0) if stats["total"] > 0 else global_prob
        shrink = stats["total"] / (stats["total"] + CALIBRATION_SHRINKAGE) if stats["total"] > 0 else 0.0
        calibrated = (shrink * local_prob) + ((1.0 - shrink) * global_prob)
        # blend a little of current model confidence so engine can adapt before dataset gets large
        blended = (0.75 * calibrated) + (0.25 * prob_from_model)
        expectancy = blended * payout - (1.0 - blended)
        return {
            "probability": round(blended, 4),
            "raw_probability": round(prob_from_model, 4),
            "source": chosen_name,
            "sample": int(stats["total"]),
            "wins": int(stats["wins"]),
            "losses": int(stats["losses"]),
            "bucket": bucket,
            "breakeven_probability": round(breakeven, 4),
            "expectancy_r": round(expectancy, 4),
            "global_probability": round(global_prob, 4),
        }
