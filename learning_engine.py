import json
import os
from storage_paths import DATA_DIR, migrate_file
from json_safe import safe_dump
from state_store import get_state_store

from config import ADAPTIVE_MIN_TRADES, ADAPTIVE_STRONG_MIN_TRADES, ADAPTIVE_PROVEN_MIN_TRADES

STATE_FILE = os.path.join(DATA_DIR, "alpha_hive_learning.json")
migrate_file(STATE_FILE, ["/tmp/nexus_learning.json", os.path.join("/opt/render/project/src/data", "alpha_hive_learning.json")])
STORE_KEY = "learning_memory"
SEGMENT_KEY = "__segments__"


class LearningEngine:
    def dynamic_signal_limit(self):
        return 5

    def __init__(self):
        self.store = get_state_store()
        self.memory = self._load()

    def _load(self):
        store_value = self.store.get_json(STORE_KEY, None)
        if isinstance(store_value, dict) and store_value:
            return store_value
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.store.set_json(STORE_KEY, data)
                        return data
            except Exception:
                return {}
        return {}

    def _save(self):
        self.store.set_json(STORE_KEY, self.memory)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            safe_dump(self.memory, f)


    def _ensure_segments(self):
        if SEGMENT_KEY not in self.memory or not isinstance(self.memory.get(SEGMENT_KEY), dict):
            self.memory[SEGMENT_KEY] = {}
        return self.memory[SEGMENT_KEY]

    def _hour_bucket(self, analysis_time):
        try:
            hour = int(str(analysis_time).split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def _segment_id(self, *, asset, analysis_time, regime, strategy_name, direction, provider, market_type):
        provider_text = str(provider or "auto").split("-")[0]
        return "|".join([
            str(asset or "N/A"),
            self._hour_bucket(analysis_time),
            str(regime or "unknown"),
            str(strategy_name or "none"),
            str(direction or "none"),
            provider_text,
            str(market_type or "unknown"),
        ])

    def _ensure_asset(self, asset):
        if not asset:
            return None
        if asset not in self.memory:
            self.memory[asset] = {"wins": 0, "loss": 0}
        return asset

    def should_filter_asset(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return False

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        wins = int(data.get("wins", 0))
        loss = int(data.get("loss", 0))
        total = wins + loss

        if total < ADAPTIVE_MIN_TRADES:
            return False

        winrate = wins / total if total else 0.0
        return winrate < 0.40 and loss >= max(12, total // 2)

    def register_result(self, signal, result):
        asset = self._ensure_asset(signal.get("asset"))
        if not asset:
            return

        win = result.get("win")
        if win is None:
            outcome = str(result.get("result", "")).upper()
            if outcome == "WIN":
                win = True
            elif outcome == "LOSS":
                win = False
            else:
                return

        if win:
            self.memory[asset]["wins"] += 1
        else:
            self.memory[asset]["loss"] += 1

        segment_id = self._segment_id(
            asset=signal.get("asset"),
            analysis_time=signal.get("analysis_time"),
            regime=signal.get("regime"),
            strategy_name=signal.get("strategy_name"),
            direction=signal.get("signal") or signal.get("direction"),
            provider=signal.get("provider"),
            market_type=signal.get("market_type"),
        )
        segments = self._ensure_segments()
        row = segments.setdefault(segment_id, {"wins": 0, "loss": 0})
        if win:
            row["wins"] += 1
        else:
            row["loss"] += 1

        self._save()

    def get_score_boost(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return 0.0

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        total = data["wins"] + data["loss"]

        if total < ADAPTIVE_MIN_TRADES:
            return 0.0

        winrate = data["wins"] / total if total else 0.0
        sample_factor = min(1.0, total / float(ADAPTIVE_PROVEN_MIN_TRADES))
        raw = (winrate - 0.5) * 1.4
        boost = max(-0.22, min(0.22, raw * sample_factor))
        return round(boost, 2)

    def get_calibration_profile(self, asset=None):
        if asset:
            asset = self._ensure_asset(asset)
            data = self.memory.get(asset, {"wins": 0, "loss": 0})
            total = data["wins"] + data["loss"]

            if total < ADAPTIVE_MIN_TRADES:
                return {
                    "confidence_factor": 1.0,
                    "aggressiveness": 1.0,
                    "min_score": 3.0,
                    "max_signals": 2,
                    "mode": "base"
                }

            winrate = data["wins"] / total
            confidence_factor = 0.95 + ((winrate - 0.5) * 0.35)
            aggressiveness = 0.95 + ((winrate - 0.5) * 0.20)

            if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate >= 0.62:
                min_score = 2.9
                max_signals = 2
                mode = "confiante"
            elif total >= ADAPTIVE_STRONG_MIN_TRADES and winrate <= 0.43:
                min_score = 3.3
                max_signals = 1
                mode = "cautela"
            else:
                min_score = 3.05
                max_signals = 2
                mode = "equilibrado"

            return {
                "confidence_factor": round(max(0.88, min(1.12, confidence_factor)), 2),
                "aggressiveness": round(max(0.88, min(1.08, aggressiveness)), 2),
                "min_score": round(min_score, 2),
                "max_signals": max_signals,
                "mode": mode
            }

        total_wins = 0
        total_loss = 0
        for data in self.memory.values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total = total_wins + total_loss
        if total < ADAPTIVE_MIN_TRADES:
            return {
                "confidence_factor": 1.0,
                "aggressiveness": 1.0,
                "min_score": 3.0,
                "max_signals": 2,
                "mode": "base"
            }

        winrate = total_wins / total if total else 0.0
        confidence_factor = 0.95 + ((winrate - 0.5) * 0.35)
        aggressiveness = 0.95 + ((winrate - 0.5) * 0.20)

        if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate >= 0.62:
            min_score = 2.9
            max_signals = 2
            mode = "confiante"
        elif total >= ADAPTIVE_STRONG_MIN_TRADES and winrate <= 0.43:
            min_score = 3.3
            max_signals = 1
            mode = "cautela"
        else:
            min_score = 3.05
            max_signals = 2
            mode = "equilibrado"

        return {
            "confidence_factor": round(max(0.88, min(1.12, confidence_factor)), 2),
            "aggressiveness": round(max(0.88, min(1.08, aggressiveness)), 2),
            "min_score": round(min_score, 2),
            "max_signals": max_signals,
            "mode": mode
        }

    def dynamic_minimum_score(self):
        profile = self.get_calibration_profile()
        return profile.get("min_score", 3.0)

    def get_adaptive_bonus(self, asset, *args, **kwargs):
        boost = self.get_score_boost(asset)
        if boost > 0.12:
            return boost, "Ativo favorável"
        if boost < -0.12:
            return boost, "Ativo fraco"
        return boost, "Histórico insuficiente"

    def should_pause_asset_temporarily(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return False

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        wins = int(data.get("wins", 0))
        loss = int(data.get("loss", 0))
        total = wins + loss

        if total < ADAPTIVE_STRONG_MIN_TRADES:
            return False

        winrate = wins / total if total else 0.0
        return loss >= max(20, int(total * 0.55)) and winrate < 0.40

    def get_rigor_penalty(self):
        total_wins = 0
        total_loss = 0
        for data in self.memory.values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total = total_wins + total_loss
        if total < ADAPTIVE_MIN_TRADES:
            return 0.0

        winrate = total_wins / total if total else 0.0

        if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate < 0.43:
            return 0.25
        if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate > 0.60:
            return -0.05
        return 0.0


def get_segment_adjustment(self, *, asset, analysis_time, regime, strategy_name, direction, provider, market_type):
    segments = self._ensure_segments()
    segment_id = self._segment_id(
        asset=asset,
        analysis_time=analysis_time,
        regime=regime,
        strategy_name=strategy_name,
        direction=direction,
        provider=provider,
        market_type=market_type,
    )
    data = segments.get(segment_id, {"wins": 0, "loss": 0})
    wins = int(data.get("wins", 0) or 0)
    loss = int(data.get("loss", 0) or 0)
    total = wins + loss
    if total < 8:
        return {"score_boost": 0.0, "confidence_shift": 0, "sample": total, "reason": "Segmentação: amostra insuficiente"}

    winrate = wins / total if total else 0.0
    edge = winrate - 0.5
    sample_factor = min(1.0, total / 40.0)
    score_boost = max(-0.18, min(0.18, edge * 0.9 * sample_factor))
    confidence_shift = int(max(-4, min(4, round(edge * 18 * sample_factor))))
    if winrate >= 0.62:
        reason = "Segmentação: contexto historicamente favorável"
    elif winrate <= 0.42:
        reason = "Segmentação: contexto historicamente fraco"
    else:
        reason = "Segmentação: contexto equilibrado"
    return {
        "score_boost": round(score_boost, 2),
        "confidence_shift": confidence_shift,
        "sample": total,
        "reason": reason,
    }
