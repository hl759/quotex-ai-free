# app.py completo conforme enviado anteriormente
# (mantido integralmente para evitar cortes no mobile)
# Copie este arquivo direto para o GitHub

# IMPORTANTE: este arquivo assume que todos os módulos existentes continuam no projeto

import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string

from scanner import MarketScanner
from data_manager import DataManager
from learning_engine import LearningEngine
from result_evaluator import ResultEvaluator
from journal_manager import JournalManager
from decision_engine import DecisionEngine
from config import ASSETS, SCAN_INTERVAL_SECONDS

app = Flask(__name__)

data_manager = DataManager()
learning = LearningEngine()
scanner = MarketScanner(data_manager, learning)
decision_engine = DecisionEngine(learning)
result_evaluator = ResultEvaluator()
journal = JournalManager()

STATE_DIR = "/tmp/nexus_state"
CURRENT_DECISION_FILE = os.path.join(STATE_DIR, "current_decision.json")
DECISION_HISTORY_FILE = os.path.join(STATE_DIR, "decision_history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

scan_count = 0
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

def decorate_decision(decision):
    analysis = now_brazil()
    entry = analysis + timedelta(minutes=1)
    expiration = entry + timedelta(minutes=1)

    return {
        "asset": decision.get("asset", "N/A"),
        "decision": decision.get("decision", "NAO_OPERAR"),
        "direction": decision.get("direction"),
        "score": decision.get("score", 0),
        "confidence": decision.get("confidence", 50),
        "regime": decision.get("regime", "unknown"),
        "analysis_time": analysis.strftime("%H:%M"),
        "entry_time": entry.strftime("%H:%M"),
        "expiration": expiration.strftime("%H:%M"),
        "reason_text": "\n".join(["• " + str(r) for r in decision.get("reasons", [])]) if decision.get("reasons") else "Sem detalhes"
    }

def save_state(current_decision, history, scans):
    write_json(CURRENT_DECISION_FILE, current_decision)
    write_json(DECISION_HISTORY_FILE, history[:50])
    write_json(META_FILE, {
        "last_scan": now_brazil().strftime("%H:%M:%S"),
        "scan_count": scans
    })

def load_state():
    current = read_json(CURRENT_DECISION_FILE, {})
    history = read_json(DECISION_HISTORY_FILE, [])
    meta = read_json(META_FILE, {"last_scan": "--", "scan_count": 0})
    return current, history, meta

def get_snapshot():
    current, history, meta = load_state()
    return {
        "current": current,
        "history": history[:20],
        "meta": {
            "last_scan": meta.get("last_scan", "--"),
            "scan_count": meta.get("scan_count", 0),
            "asset_count": len(ASSETS),
        },
        "learning_stats": journal.stats(),
        "best_assets": journal.best_assets(),
        "best_hours": journal.best_hours(),
    }

def scanner_loop():
    global scan_count
    while True:
        try:
            market = scanner.scan_assets()
            decisions = []

            for item in market:
                asset = item.get("asset")
                indicators = item.get("indicators", {})
                decision = decision_engine.decide(asset, indicators)
                decision["provider"] = item.get("provider", "auto")
                decisions.append((decision, item))

            decisions.sort(key=lambda x: (x[0].get("score", 0), x[0].get("confidence", 0)), reverse=True)

            if decisions:
                best_decision_raw, matched_market = decisions[0]
            else:
                best_decision_raw, matched_market = ({
                    "asset": "MERCADO",
                    "decision": "NAO_OPERAR",
                    "direction": None,
                    "score": 0,
                    "confidence": 50,
                    "regime": "unknown",
                    "reasons": ["Sem dados suficientes no momento"]
                }, None)

            decorated = decorate_decision(best_decision_raw)

            if matched_market and decorated["decision"] in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
                result_data = result_evaluator.evaluate(best_decision_raw, matched_market.get("candles", []))
                if result_data:
                    safe_signal = {
                        "asset": decorated["asset"],
                        "signal": decorated["direction"],
                        "score": decorated["score"],
                        "confidence": decorated["confidence"],
                        "provider": best_decision_raw.get("provider", "auto"),
                        "analysis_time": decorated["analysis_time"],
                        "entry_time": decorated["entry_time"],
                        "expiration": decorated["expiration"],
                    }
                    learning.register_result(safe_signal, result_data)

            history = read_json(DECISION_HISTORY_FILE, [])
            history = [decorated] + history

            scan_count += 1
            save_state(decorated, history, scan_count)

            print(f"Scan #{scan_count} | Decision: {decorated['decision']} | Asset: {decorated['asset']}", flush=True)
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
    return jsonify(get_snapshot())

@app.route("/health")
def health():
    ensure_scanner_started()
    return {"status": "running"}

if __name__ == "__main__":
    ensure_scanner_started()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
