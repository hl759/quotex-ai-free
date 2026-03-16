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


def normalize_signals(signals):
    normalized = []

    for s in signals:
        analysis = datetime.utcnow() - timedelta(hours=3)
        entry = analysis + timedelta(minutes=1)
        expiration = entry + timedelta(minutes=1)

        reason = s.get("reason", [])
        if isinstance(reason, list):
            reason_text = "\n".join(["• " + str(r) for r in reason]) if reason else "Sem detalhes"
        else:
            reason_text = str(reason)

        normalized.append({
            "asset": s.get("asset"),
            "signal": s.get("signal"),
            "score": s.get("score", 0),
            "confidence": s.get("confidence", 50),
            "provider": s.get("provider", "auto"),
            "analysis_time": analysis.strftime("%H:%M"),
            "entry_time": entry.strftime("%H:%M"),
            "expiration": expiration.strftime("%H:%M"),
            "reason_text": reason_text
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

            if raw_signals:
                learning.update_stats(raw_signals)

                for signal in raw_signals:
                    matched_asset = None

                    for item in market:
                        if item.get("asset") == signal.get("asset"):
                            matched_asset = item
                            break

                    if matched_asset:
                        result_data = result_evaluator.evaluate(signal, matched_asset.get("candles", []))
                        if result_data:
                            learning.register_result(signal, result_data)

            history = read_json(SIGNAL_HISTORY_FILE, [])

            if signals:
                history = signals + history

            scan_count += 1
            last_scan_time = datetime.utcnow
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

# ================================
# INICIALIZAÇÃO
# ================================

data_manager = DataManager()
learning = LearningEngine()
scanner = MarketScanner(data_manager)
signal_engine = SignalEngine(learning)
result_evaluator = ResultEvaluator()
journal = JournalManager()

# ================================
# ESTADO
# ================================

STATE_DIR = "/tmp/nexus_state"

LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

scan_count = 0
last_scan_time = None


# ================================
# FUNÇÕES
# ================================

def read_json(path, default):

    try:
        with open(path, "r") as f:
            return json.load(f)

    except:
        return default


def write_json(path, data):

    with open(path, "w") as f:
        json.dump(data, f)


def normalize_signals(signals):

    normalized = []

    for s in signals:

        analysis = datetime.utcnow() - timedelta(hours=3)

        entry = analysis + timedelta(minutes=1)

        expiration = entry + timedelta(minutes=1)

        reason = s.get("reason", [])

        if isinstance(reason, list):
            reason_text = "\n".join(reason)
        else:
            reason_text = str(reason)

        normalized.append({

            "asset": s.get("asset"),
            "signal": s.get("signal"),
            "score": s.get("score", 0),
            "confidence": s.get("confidence", 50),

            "analysis_time": analysis.strftime("%H:%M"),
            "entry_time": entry.strftime("%H:%M"),
            "expiration": expiration.strftime("%H:%M"),

            "reason_text": reason_text

        })

    return normalized


# ================================
# SALVAR ESTADO
# ================================

def save_state(signals, history, scan_time, scans):

    write_json(LATEST_SIGNALS_FILE, signals)

    write_json(SIGNAL_HISTORY_FILE, history[:30])

    write_json(META_FILE, {

        "last_scan": scan_time.strftime("%H:%M:%S"),

        "scan_count": scans

    })


def load_state():

    signals = read_json(LATEST_SIGNALS_FILE, [])

    history = read_json(SIGNAL_HISTORY_FILE, [])

    meta = read_json(META_FILE, {

        "last_scan": "--",

        "scan_count": 0

    })

    return signals, history, meta


# ================================
# LOOP DO SCANNER
# ================================

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

            last_scan_time = datetime.utcnow()

            save_state(signals, history, last_scan_time, scan_count)

            print("Scan #%s | Signals: %s" % (scan_count, len(signals)), flush=True)

        except Exception as e:

            print("Scanner error:", e, flush=True)

        time.sleep(SCAN_INTERVAL_SECONDS)


# ================================
# LAYOUT PREMIUM
# ================================

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>

<meta name="viewport" content="width=device-width, initial-scale=1">

<title>NEXUS AI</title>

<style>

body{
margin:0;
background:#071426;
color:white;
font-family:Arial;
}

.container{
padding:20px;
max-width:700px;
margin:auto;
}

.card{
background:#0d2039;
border-radius:20px;
padding:20px;
margin-bottom:20px;
}

.title{
font-size:30px;
font-weight:700;
}

.subtitle{
color:#9db3cf;
margin-bottom:20px;
}

.grid{
display:grid;
grid-template-columns:1fr 1fr;
gap:12px;
}

.stat{
background:#132c4b;
padding:15px;
border-radius:12px;
}

.stat-title{
font-size:12px;
color:#9db3cf;
}

.stat-value{
font-size:22px;
font-weight:700;
}

.signal{
background:#132c4b;
border-radius:12px;
padding:15px;
margin-top:10px;
}

.call{
background:#19e59f;
color:#043a2a;
padding:5px 10px;
border-radius:8px;
font-weight:700;
}

.put{
background:#ff7b8a;
color:#3c0e16;
padding:5px 10px;
border-radius:8px;
font-weight:700;
}

.reason{
margin-top:10px;
font-size:13px;
color:#9db3cf;
}

</style>

</head>

<body>

<div class="container">

<div class="card">

<div class="title">NEXUS AI v10.1</div>
<div class="subtitle">ULTRA ROBUSTA</div>

<div class="grid">

<div class="stat">
<div class="stat-title">Último scan</div>
<div class="stat-value">{{last_scan}}</div>
</div>

<div class="stat">
<div class="stat-title">Scans</div>
<div class="stat-value">{{scan_count}}</div>
</div>

<div class="stat">
<div class="stat-title">Sinais</div>
<div class="stat-value">{{signal_count}}</div>
</div>

<div class="stat">
<div class="stat-title">Ativos</div>
<div class="stat-value">{{asset_count}}</div>
</div>

</div>

</div>

{% for s in signals %}

<div class="card signal">

<strong>{{s.asset}}</strong>

<br><br>

{% if s.signal == "CALL" %}
<span class="call">CALL</span>
{% else %}
<span class="put">PUT</span>
{% endif %}

<br><br>

Score: {{s.score}}  
Confiança: {{s.confidence}}%

<br><br>

Análise: {{s.analysis_time}}  
Entrada: {{s.entry_time}}  
Expiração: {{s.expiration}}

<div class="reason">
{{s.reason_text}}
</div>

</div>

{% endfor %}

</div>

</body>
</html>
"""


# ================================
# ROTAS
# ================================

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


# ================================
# THREAD
# ================================

thread = threading.Thread(target=scanner_loop, daemon=True)

thread.start()


# ================================
# START SERVER
# ================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
