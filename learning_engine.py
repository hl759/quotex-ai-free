import json
import os
from datetime import datetime

from storage_paths import DATA_DIR, migrate_file
from json_safe import safe_dump
from state_store import get_state_store

from config import ADAPTIVE_MIN_TRADES, ADAPTIVE_STRONG_MIN_TRADES, ADAPTIVE_PROVEN_MIN_TRADES

STATE_FILE = os.path.join(DATA_DIR, "alpha_hive_learning.json")
migrate_file(STATE_FILE, ["/tmp/nexus_learning.json", os.path.join("/opt/render/project/src/data", "alpha_hive_learning.json")])
STORE_KEY = "learning_memory"
SEGMENTS_KEY = "__segments__"
META_KEY = "__meta__"


class LearningEngine:
    def dynamic_signal_limit(self):
        return 5

    def __init__(self):
        self.store = get_state_store()
        self.memory = self._load()

    def _reserved_keys(self):
        return {SEGMENTS_KEY, META_KEY}

    def _load(self):
        store_value = self.store.get_json(STORE_KEY, None)
        if isinstance(store_value, dict) and store_value:
            store_value.setdefault(SEGMENTS_KEY, {})
            store_value.setdefault(META_KEY, {})
            return store_value
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault(SEGMENTS_KEY, {})
                        data.setdefault(META_KEY, {})
                        self.store.set_json(STORE_KEY, data)
                        return data
            except Exception:
                return {SEGMENTS_KEY: {}, META_KEY: {}}
        return {SEGMENTS_KEY: {}, META_KEY: {}}

    def _save(self):
        self.store.set_json(STORE_KEY, self.memory)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            safe_dump(self.memory, f)

    def _asset_items(self):
        return {k: v for k, v in self.memory.items() if k not in self._reserved_keys() and isinstance(v, dict)}

    def _ensure_asset(self, asset):
        if not asset:
            return None
        if asset not in self.memory or asset in self._reserved_keys():
            self.memory[asset] = {"wins": 0, "loss": 0}
        return asset

    def _segment_store(self):
        if SEGMENTS_KEY not in self.memory or not isinstance(self.memory.get(SEGMENTS_KEY), dict):
            self.memory[SEGMENTS_KEY] = {}
        return self.memory[SEGMENTS_KEY]

    def _safe_hour_bucket(self, analysis_time):
        try:
            text = str(analysis_time or "").strip()
            if ":" not in text:
                return "unknown"
            hour = int(text.split(":")[0])
            return f"{hour:02d}:00" if 0 <= hour <= 23 else "unknown"
        except Exception:
            return "unknown"

    def _segment_key(self, asset, direction, regime, strategy_name, analysis_time, provider=None, market_type=None):
        parts = [
            str(asset or "unknown"),
            str(direction or "unknown"),
            str(regime or "unknown"),
            str(strategy_name or "none"),
            self._safe_hour_bucket(analysis_time),
            str(provider or "unknown"),
            str(market_type or "unknown"),
        ]
        return "|".join(parts)

    def _clip(self, value, low, high):
        return max(low, min(high, value))

    def _stats(self, wins, loss):
        total = int(wins or 0) + int(loss or 0)
        winrate = (int(wins or 0) / total) if total else 0.0
        return total, winrate

    def _compute_boost(self, wins, loss, min_trades, proven_trades, cap):
        total, winrate = self._stats(wins, loss)
        if total < min_trades:
            return 0.0, total, winrate
        sample_factor = min(1.0, total / float(max(proven_trades, min_trades)))
        raw = (winrate - 0.5) * 1.2
        return round(self._clip(raw * sample_factor, -cap, cap), 2), total, winrate

    def should_filter_asset(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return False

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        wins = int(data.get("wins", 0))
        loss = int(data.get("loss", 0))
        total, winrate = self._stats(wins, loss)

        if total < ADAPTIVE_MIN_TRADES:
            return False

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

        segment_key = self._segment_key(
            asset=signal.get("asset"),
            direction=signal.get("signal") or signal.get("direction"),
            regime=signal.get("regime"),
            strategy_name=signal.get("strategy_name"),
            analysis_time=signal.get("analysis_time") or signal.get("analysis_session"),
            provider=signal.get("provider"),
            market_type=signal.get("market_type"),
        )
        segment_store = self._segment_store()
        current = segment_store.setdefault(segment_key, {"wins": 0, "loss": 0, "updated_at": ""})
        if win:
            current["wins"] = int(current.get("wins", 0)) + 1
        else:
            current["loss"] = int(current.get("loss", 0)) + 1
        current["updated_at"] = datetime.utcnow().isoformat()
        current["asset"] = signal.get("asset")
        current["direction"] = signal.get("signal") or signal.get("direction")
        current["regime"] = signal.get("regime")
        current["strategy_name"] = signal.get("strategy_name")
        current["hour_bucket"] = self._safe_hour_bucket(signal.get("analysis_time") or signal.get("analysis_session"))
        current["provider"] = signal.get("provider")
        current["market_type"] = signal.get("market_type")

        self._save()

    def get_score_boost(self, asset):
        asset = self._ensure_asset(asset)
        if not asset:
            return 0.0

        data = self.memory.get(asset, {"wins": 0, "loss": 0})
        boost, _, _ = self._compute_boost(data.get("wins", 0), data.get("loss", 0), ADAPTIVE_MIN_TRADES, ADAPTIVE_PROVEN_MIN_TRADES, 0.22)
        return boost

    def get_segment_adjustment(self, asset=None, direction=None, regime=None, strategy_name=None, analysis_time=None, provider=None, market_type=None):
        key = self._segment_key(asset, direction, regime, strategy_name, analysis_time, provider, market_type)
        row = self._segment_store().get(key, {})
        wins = int(row.get("wins", 0) or 0)
        loss = int(row.get("loss", 0) or 0)
        total, winrate = self._stats(wins, loss)
        if total < max(6, ADAPTIVE_MIN_TRADES // 4):
            return {
                "score_boost": 0.0,
                "confidence_shift": 0,
                "proof_state": "building",
                "reason": "Ajuste por segmento indisponível",
                "key": key,
                "trades": total,
                "winrate": round(winrate * 100, 2),
            }

        sample_factor = min(1.0, total / float(max(ADAPTIVE_STRONG_MIN_TRADES // 2, 12)))
        raw = (winrate - 0.5) * 0.75
        score_boost = round(self._clip(raw * sample_factor, -0.14, 0.14), 2)
        confidence_shift = int(round(self._clip((winrate - 0.5) * 18 * sample_factor, -4, 4)))

        if winrate >= 0.62 and total >= max(10, ADAPTIVE_MIN_TRADES // 3):
            proof_state = "proven_positive"
            reason = f"Ajuste por segmento favorável ({round(winrate * 100, 1)}%)"
        elif winrate <= 0.42 and total >= max(10, ADAPTIVE_MIN_TRADES // 3):
            proof_state = "proven_negative"
            reason = f"Ajuste por segmento defensivo ({round(winrate * 100, 1)}%)"
        else:
            proof_state = "building"
            reason = f"Segmento em construção ({total} casos)"

        return {
            "score_boost": score_boost,
            "confidence_shift": confidence_shift,
            "proof_state": proof_state,
            "reason": reason,
            "key": key,
            "trades": total,
            "winrate": round(winrate * 100, 2),
        }

    def get_calibration_profile(self, asset=None):
        if asset:
            asset = self._ensure_asset(asset)
            data = self.memory.get(asset, {"wins": 0, "loss": 0})
            total, winrate = self._stats(data.get("wins", 0), data.get("loss", 0))

            if total < ADAPTIVE_MIN_TRADES:
                return {
                    "confidence_factor": 1.0,
                    "aggressiveness": 1.0,
                    "min_score": 3.0,
                    "max_signals": 2,
                    "mode": "base"
                }

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
        for data in self._asset_items().values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total, winrate = self._stats(total_wins, total_loss)
        if total < ADAPTIVE_MIN_TRADES:
            return {
                "confidence_factor": 1.0,
                "aggressiveness": 1.0,
                "min_score": 3.0,
                "max_signals": 2,
                "mode": "base"
            }

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
        total, winrate = self._stats(data.get("wins", 0), data.get("loss", 0))

        if total < ADAPTIVE_STRONG_MIN_TRADES:
            return False

        loss = int(data.get("loss", 0))
        return loss >= max(20, int(total * 0.55)) and winrate < 0.40

    def get_rigor_penalty(self):
        total_wins = 0
        total_loss = 0
        for data in self._asset_items().values():
            total_wins += int(data.get("wins", 0))
            total_loss += int(data.get("loss", 0))

        total, winrate = self._stats(total_wins, total_loss)
        if total < ADAPTIVE_MIN_TRADES:
            return 0.0

        if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate < 0.43:
            return 0.25
        if total >= ADAPTIVE_STRONG_MIN_TRADES and winrate > 0.60:
            return -0.05
        return 0.0
