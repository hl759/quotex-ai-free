import json
import os
import threading
import time
from result_evaluator import ResultEvaluator
from journal_manager import JournalManager
from datetime import datetime
from flask import Flask, jsonify, render_template_string

from scanner import MarketScanner
from signal_engine import SignalEngine
from data_manager import DataManager
from learning_engine import LearningEngine
from config import ASSETS, SCAN_INTERVAL_SECONDS

app = Flask(__name__)

data_manager = DataManager()
scanner = MarketScanner(data_manager)
signal_engine = SignalEngine()
learning = LearningEngine()
result_evaluator = ResultEvaluator()
journal = JournalManager()

STATE_DIR = "/tmp/nexus_state"
LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "signal_history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

scan_count = 0
last_scan_time = None

HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NEXUS-AI</title>
  <style>
    body{margin:0;font-family:Arial,sans-serif;background:#06111f;color:#eef4ff}
    .wrap{max-width:760px;margin:0 auto;padding:16px}
    .card{background:#0b1b30;border:1px solid rgba(0,255,200,.12);border-radius:20px;padding:16px;margin-bottom:16px}
    .title{font-size:28px;font-weight:900}
    .title span{color:#19f0d1}
    .muted{color:#91a4c3}
    .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:16px}
    .item{background:#10233c;border-radius:14px;padding:12px}
    .label{font-size:12px;color:#91a4c3;text-transform:uppercase;margin-bottom:6px}
    .value{font-size:22px;font-weight:800}
    .signal{background:#10233c;border-radius:16px;padding:14px;margin-top:12px}
    .badge{display:inline-block;padding:8px 12px;border-radius:999px;font-weight:800;font-size:13px}
    .call{background:#1df2a4;color:#062116}
    .put{background:#ff7b8c;color:#311016}
    pre{white-space:pre-wrap;word-break:break-word}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="title">NEXUS-<span>AI</span></div>
      <div class="muted">Modo estável</div>

      <div class="grid">
        <div class="item">
          <div class="label">Último scan</div>
          <div class="value">{{ last_scan }}</div>
        </div>
        <div class="item">
          <div class="label">Scans</div>
          <div class="value">{{ scan_count }}</div>
        </div>
        <div class="item">
          <div class="label">Sinais</div>
          <div class="value">{{ signal_count }}</div>
        </div>
        <div class="item">
          <div class="label">Ativos</div>
          <div class="value">{{ asset_count }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="label">Status das APIs</div>
      <div class="muted">
        Twelve congelada: <strong>{{ "SIM" if usage.twelve_frozen else "NÃO" }}</strong><br>
        Twelve pausa minuto: <strong>{{ "SIM" if usage.twelve_minute_paused else "NÃO" }}</strong><br>
        Finnhub congelada: <strong>{{ "SIM" if usage.finnhub_frozen else "NÃO" }}</strong><br>
        Alpha congelada: <strong>{{ "SIM" if usage.alpha_frozen else "NÃO" }}</strong>
      </div>
    </div>

    <div class="card">
      <div class="label">Sinais atuais</div>
      {% if signals %}
        {% for s in signals %}
          <div class="signal">
            <strong>{{ s.asset }}</strong>
            <div style="margin:8px 0;">
              <span class="badge {% if s.signal == 'CALL' %}call{% else %}put{% endif %}">{{ s.signal }}</span>
            </div>
            Análise: {{ s.analysis_time }}<br>
            Entrada: {{ s.entry_time }}<br>
            Expiração: {{ s.expiration }}<br>
            Score: {{ s.score }} · Confiança: {{ s.confidence }}% · Fonte: {{ s.provider }}
            <pre>{{ s.reason_text }}</pre>
          </div>
        {% endfor %}
      {% else %}
        <div class="muted">Nenhum sinal disponível agora.</div>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""

def read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json_file(path, data):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, path)

def normalize_signals(signals):
    normalized = []
    for s in signals:
        reason = s.get("reason", [])
        if isinstance(reason, list):
            reason_text = "\\n".join(["• " + str(item) for item in reason]) if reason else "Sem detalhes"
        else:
            reason_text = str(reason)

        normalized.append({
            "asset": str(s.get("asset", "N/A")),
            "signal": str(s.get("signal", "CALL")),
            "score": s.get("score", 0),
            "confidence": int(s.get("confidence", 50)),
            "timeframe": str(s.get("timeframe", "M1")),
            "analysis_time": str(s.get("analysis_time", "--:--")),
            "entry_time": str(s.get("entry_time", "--:--")),
            "expiration": str(s.get("expiration", "--:--")),
            "generated_at": str(s.get("generated_at", datetime.now().strftime("%H:%M:%S"))),
            "provider": str(s.get("provider", "auto")),
            "reason_text": reason_text
        })
    return normalized

def save_state(signals, history, scan_time, scan_count_value):
    write_json_file(LATEST_SIGNALS_FILE, signals)
    write_json_file(SIGNAL_HISTORY_FILE, history[:20])
    write_json_file(META_FILE, {
        "last_scan": scan_time.strftime("%H:%M:%S") if scan_time else "--",
        "scan_count": scan_count_value
    })

def load_state():
    signals = read_json_file(LATEST_SIGNALS_FILE, [])
    history = read_json_file(SIGNAL_HISTORY_FILE, [])
    meta = read_json_file(META_FILE, {"last_scan": "--", "scan_count": 0})
    return signals, history, meta

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
                                "Result evaluated | %s | %s | %s" % (
                                    signal.get("asset"),
                                    signal.get("signal"),
                                    result_data.get("result")
                                ),
                                flush=True
                            )

            current_history = read_json_file(SIGNAL_HISTORY_FILE, [])
            if normalized:
                current_history = (normalized + current_history)[:20]

            last_scan_time = datetime.now()
            scan_count += 1

            save_state(normalized, current_history, last_scan_time, scan_count)
            print("Scan #%s | Signals: %s" % (scan_count, len(normalized)), flush=True)

        except Exception as e:
            print("Scanner error: %s" % e, flush=True)

        time.sleep(SCAN_INTERVAL_SECONDS)
def home():
    signals, _, meta = load_state()
    usage = data_manager.get_usage_snapshot()

    template_usage = {
        "twelve_frozen": usage.get("twelve_frozen", False),
        "twelve_minute_paused": usage.get("twelve_minute_paused", False),
        "finnhub_frozen": usage.get("finnhub_frozen", False),
        "alpha_frozen": usage.get("alpha_frozen", False),
    }

    return render_template_string(
        HTML_PAGE,
        signals=signals,
        last_scan=meta.get("last_scan", "--"),
        scan_count=meta.get("scan_count", 0),
        signal_count=len(signals),
        asset_count=len(ASSETS),
        usage=template_usage
    )

@app.route("/health")
def health():
    return {"status": "NEXUS running"}

@app.route("/signals")
def signals():
    signals, _, _ = load_state()
    return jsonify(signals)

@app.route("/usage")
def usage():
    return jsonify(data_manager.get_usage_snapshot())

thread = threading.Thread(target=scanner_loop, daemon=True)
thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
