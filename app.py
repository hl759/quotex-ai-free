import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string

from scanner import MarketScanner
from signal_engine import SignalEngine
from data_manager import DataManager
from learning_engine import LearningEngine
from result_evaluator import ResultEvaluator
from journal_manager import JournalManager
from config import ASSETS, SCAN_INTERVAL_SECONDS

app = Flask(__name__)

data_manager = DataManager()
learning = LearningEngine()
scanner = MarketScanner(data_manager)
signal_engine = SignalEngine(learning)
result_evaluator = ResultEvaluator()
journal = JournalManager()

STATE_DIR = "/tmp/nexus_state"
LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

scan_count = 0
last_scan_time = None
scanner_started = False
scanner_lock = threading.Lock()

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)

def now_brazil():
    return datetime.utcnow() - timedelta(hours=3)

def normalize_signals(signals):
    normalized = []
    for s in signals:
        analysis = now_brazil()
        entry = analysis + timedelta(minutes=1)
        expiration = entry + timedelta(minutes=1)

        normalized.append({
            "asset": s.get("asset", "N/A"),
            "signal": s.get("signal", "CALL"),
            "score": s.get("score", 0),
            "confidence": s.get("confidence", 50),
            "provider": s.get("provider", "auto"),
            "analysis_time": analysis.strftime("%H:%M"),
            "entry_time": entry.strftime("%H:%M"),
            "expiration": expiration.strftime("%H:%M"),
            "reason_text": str(s.get("reason", "Sem detalhes"))
        })
    return normalized

def save_state(signals, history, scan_time, scans):
    write_json(LATEST_SIGNALS_FILE, signals)
    write_json(SIGNAL_HISTORY_FILE, history[:50])
    write_json(META_FILE, {
        "last_scan": scan_time.strftime("%H:%M:%S"),
        "scan_count": scans
    })

def load_state():
    signals = read_json(LATEST_SIGNALS_FILE, [])
    history = read_json(SIGNAL_HISTORY_FILE, [])
    meta = read_json(META_FILE, {"last_scan": "--", "scan_count": 0})
    return signals, history, meta

def scanner_loop():
    global scan_count, last_scan_time
    while True:
        try:
            market = scanner.scan_assets()
            raw_signals = signal_engine.generate_signals(market)
            signals = normalize_signals(raw_signals if raw_signals else [])

            history = read_json(SIGNAL_HISTORY_FILE, [])
            if signals:
                history = signals + history

            scan_count += 1
            last_scan_time = now_brazil()

            save_state(signals, history, last_scan_time, scan_count)

            print(f"Scan #{scan_count} | Signals: {len(signals)}", flush=True)
            time.sleep(SCAN_INTERVAL_SECONDS)

        except Exception as e:
            print("Scanner error:", e, flush=True)
            time.sleep(2)

def ensure_scanner_started():
    global scanner_started
    if scanner_started:
        return
    with scanner_lock:
        if scanner_started:
            return
        threading.Thread(target=scanner_loop, daemon=True).start()
        scanner_started = True

@app.before_request
def _boot():
    ensure_scanner_started()

@app.route("/")
def home():
    ensure_scanner_started()
    signals, history, meta = load_state()
    return jsonify({
        "signals": signals,
        "history": history[:10],
        "meta": meta
    })

@app.route("/health")
def health():
    return {"status": "running"}

if __name__ == "__main__":
    ensure_scanner_started()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
