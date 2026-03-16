import json
import os

STATE_DIR = "/tmp/nexus_learning"
PENDING_FILE = os.path.join(STATE_DIR, "pending_signals.json")
RESULTS_FILE = os.path.join(STATE_DIR, "results.json")
STATS_FILE = os.path.join(STATE_DIR, "stats.json")
os.makedirs(STATE_DIR, exist_ok=True)

class LearningEngine:
    def __init__(self):
        self._ensure_files()

    def _ensure_files(self):
        defaults = [
            (PENDING_FILE, []),
            (RESULTS_FILE, []),
            (STATS_FILE, {"wins": 0, "losses": 0, "by_asset": {}, "by_hour": {}, "by_provider": {}}),
        ]
        for path, default in defaults:
            if not os.path.exists(path):
                self._write_json(path, default)

    def _read_json(self, path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json(self, path, data):
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, path)

    def register_pending_signals(self, signals):
        pending = self._read_json(PENDING_FILE, [])
        existing_ids = {item.get("signal_id") for item in pending}
        for signal in signals:
            if signal.get("signal_id") not in existing_ids:
                pending.append(signal)
        self._write_json(PENDING_FILE, pending)

    def get_pending_signals(self):
        return self._read_json(PENDING_FILE, [])

    def remove_pending_signal(self, signal_id):
        pending = [item for item in self._read_json(PENDING_FILE, []) if item.get("signal_id") != signal_id]
        self._write_json(PENDING_FILE, pending)

    def _update_bucket(self, bucket, key, result):
        if key not in bucket:
            bucket[key] = {"wins": 0, "losses": 0}
        if result == "WIN":
            bucket[key]["wins"] += 1
        elif result == "LOSS":
            bucket[key]["losses"] += 1

    def save_result(self, result_record):
        results = self._read_json(RESULTS_FILE, [])
        results.insert(0, result_record)
        self._write_json(RESULTS_FILE, results[:200])
        stats = self._read_json(STATS_FILE, {"wins": 0, "losses": 0, "by_asset": {}, "by_hour": {}, "by_provider": {}})
        result = result_record.get("result")
        asset = result_record.get("asset", "N/A")
        hour = str(result_record.get("entry_time", "--:--"))[:2]
        provider = result_record.get("provider", "auto")
        if result == "WIN":
            stats["wins"] += 1
        elif result == "LOSS":
            stats["losses"] += 1
        self._update_bucket(stats["by_asset"], asset, result)
        self._update_bucket(stats["by_hour"], hour, result)
        self._update_bucket(stats["by_provider"], provider, result)
        self._write_json(STATS_FILE, stats)

    def get_recent_history(self, limit=50):
        return self._read_json(RESULTS_FILE, [])[:limit]

    def _best_key(self, bucket):
        best_name = "-"
        best_rate = -1
        for key, value in bucket.items():
            wins = value.get("wins", 0)
            losses = value.get("losses", 0)
            total = wins + losses
            if total < 3:
                continue
            rate = wins / total
            if rate > best_rate:
                best_rate = rate
                best_name = f"{key} ({round(rate*100,1)}%)"
        return best_name

    def get_summary_stats(self):
        stats = self._read_json(STATS_FILE, {"wins": 0, "losses": 0, "by_asset": {}, "by_hour": {}, "by_provider": {}})
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total = wins + losses
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0
        return {
            "wins": wins,
            "losses": losses,
            "total_evaluated": total,
            "win_rate": win_rate,
            "pending_count": len(self.get_pending_signals()),
            "best_asset": self._best_key(stats.get("by_asset", {})),
            "best_hour": self._best_key(stats.get("by_hour", {})),
            "best_provider": self._best_key(stats.get("by_provider", {})),
        }

    def get_top_assets(self, limit=8):
        stats = self._read_json(STATS_FILE, {"by_asset": {}})
        rows = []
        for asset, value in stats.get("by_asset", {}).items():
            wins = value.get("wins", 0)
            losses = value.get("losses", 0)
            total = wins + losses
            if total == 0:
                continue
            rows.append({"name": asset, "value": f"{round((wins / total) * 100, 1)}% WR"})
        rows.sort(key=lambda x: float(x["value"].replace("% WR", "")), reverse=True)
        return rows[:limit] if rows else [{"name": "Sem dados", "value": "--"}]

    def _bucket_bonus(self, bucket, texts, label):
        wins = bucket.get("wins", 0)
        losses = bucket.get("losses", 0)
        total = wins + losses
        if total < 5:
            return 0.0
        wr = wins / total
        if wr >= 0.65:
            texts.append(label)
            return 0.5
        if wr <= 0.40:
            texts.append(label + " fraca")
            return -0.5
        return 0.0

    def get_adaptive_bonus(self, asset, provider):
        stats = self._read_json(STATS_FILE, {"by_asset": {}, "by_provider": {}})
        texts = []
        bonus = self._bucket_bonus(stats.get("by_asset", {}).get(asset, {}), texts, "Ativo forte")
        bonus += self._bucket_bonus(stats.get("by_provider", {}).get(provider, {}), texts, "Fonte forte")
        return bonus, " · ".join(texts) if texts else ""

    def get_learning_export(self):
        return {"pending": self.get_pending_signals(), "results": self.get_recent_history(limit=100), "summary": self.get_summary_stats()}
