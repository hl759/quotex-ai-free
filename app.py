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

# =========================
# INICIALIZAÇÃO CORRETA
# =========================

data_manager = DataManager()

learning = LearningEngine()

scanner = MarketScanner(data_manager)

signal_engine = SignalEngine(learning)

result_evaluator = ResultEvaluator()

journal = JournalManager()

# =========================
# ESTADO
# =========================

STATE_DIR = "/tmp/nexus_state"
LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "signal_history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

scan_count = 0
last_scan_time = None

# =========================
# FUNÇÕES DE ARQUIVO
# =========================

def read_json_file(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def write_json_file(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

# =========================
# NORMALIZAÇÃO DE SINAIS
# =========================

def normalize_signals(signals):

    normalized = []

    for s in signals:

        analysis_time = datetime.utcnow() - timedelta(hours=3)

        entry_time = analysis_time + timedelta(minutes=1)

        expiration = entry_time + timedelta(minutes=1)

        reason = s.get("reason", [])

        if isinstance(reason, list):
            reason_text = "\n".join(["• " + str(r) for r in reason])
        else:
            reason_text = str(reason)

        normalized.append({
            "asset": s.get("asset"),
            "signal": s.get("signal"),
            "score": s.get("score", 0),
            "confidence": s.get("confidence", 50),
            "provider": s.get("provider", "auto"),
            "analysis_time": analysis_time.strftime("%H:%M"),
            "entry_time": entry_time.strftime("%H:%M"),
            "expiration": expiration.strftime("%H:%M"),
            "reason_text": reason_text
        })

    return normalized

# =========================
# SALVAR ESTADO
# =========================

def save_state(signals, history, scan_time, scan_count_value):

    write_json_file(LATEST_SIGNALS_FILE, signals)

    write_json_file(SIGNAL_HISTORY_FILE, history[:50])

    write_json_file(META_FILE, {
        "last_scan": scan_time.strftime("%H:%M:%S"),
        "scan_count": scan_count_value
    })

# =========================
# CARREGAR ESTADO
# =========================

def load_state():

    signals = read_json_file(LATEST_SIGNALS_FILE, [])

    history = read_json_file(SIGNAL_HISTORY_FILE, [])

    meta = read_json_file(META_FILE, {"last_scan": "--", "scan_count": 0})

    return signals, history, meta

# =========================
# SCANNER LOOP
# =========================

def scanner_loop():

    global last_scan_time, scan_count

    while True:

        try:

            raw_market_data = scanner.scan_assets()

            raw_signals = signal_engine.generate_signals(raw_market_data)

            normalized = normalize_signals(raw_signals if raw_signals else [])

            if raw_signals:

                learning.update_stats(raw_signals)

                for signal in raw_signals:

                    matched_asset = None

                    for item in raw_market_data:

                        if item.get("asset") == signal.get("asset"):

                            matched_asset = item

                            break

                    if matched_asset:

                        result_data = result_evaluator.evaluate(signal, matched_asset.get("candles", []))

                        if result_data:

                            learning.register_result(signal, result_data)

                            print(
                                "Result evaluated | %s | %s | %s"
                                % (
                                    signal.get("asset"),
                                    signal.get("signal"),
                                    result_data.get("result")
                                ),
                                flush=True
                            )

            history = read_json_file(SIGNAL_HISTORY_FILE, [])

            if normalized:

                history = normalized + history

            last_scan_time = datetime.utcnow()

            scan_count += 1

            save_state(normalized, history, last_scan_time, scan_count)

            print("Scan #%s | Signals: %s" % (scan_count, len(normalized)), flush=True)

        except Exception as e:

            print("Scanner error:", e, flush=True)

        time.sleep(SCAN_INTERVAL_SECONDS)

# =========================
# HTML
# =========================

HTML_PAGE = """
<html>
<head>
<title>NEXUS AI</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#06101f;color:white;font-family:Arial;padding:20px}
.card{background:#0c1c30;padding:20px;border-radius:15px;margin-bottom:15px}
</style>
</head>
<body>

<h2>NEXUS AI v10.1</h2>

<div class="card">
Último scan: {{last_scan}}<br>
Scans: {{scan_count}}<br>
Sinais: {{signal_count}}<br>
Ativos: {{asset_count}}
</div>

{% for s in signals %}
<div class="card">
<b>{{s.asset}}</b><br>
Sinal: {{s.signal}}<br>
Score: {{s.score}}<br>
Confiança: {{s.confidence}}%<br>
Análise: {{s.analysis_time}}<br>
Entrada: {{s.entry_time}}<br>
Expiração: {{s.expiration}}<br>
<pre>{{s.reason_text}}</pre>
</div>
{% endfor %}

</body>
</html>
"""

# =========================
# ROTAS
# =========================

@app.route("/")
def home():

    signals, history, meta = load_state()

    return render_template_string(
        HTML_PAGE,
        signals=signals,
        last_scan=meta.get("last_scan"),
        scan_count=meta.get("scan_count"),
        signal_count=len(signals),
        asset_count=len(ASSETS)
    )

@app.route("/health")
def health():

    return {"status": "running"}

@app.route("/signals")
def signals():

    signals, _, _ = load_state()

    return jsonify(signals)

@app.route("/learning-stats")
def learning_stats():

    return jsonify(journal.stats())

@app.route("/best-assets")
def best_assets():

    return jsonify(journal.best_assets())

# =========================
# THREAD
# =========================

thread = threading.Thread(target=scanner_loop, daemon=True)

thread.start()

# =========================
# START SERVER
# =========================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
