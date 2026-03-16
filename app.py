import json
import os
import threading
import time
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

STATE_DIR = "/tmp/nexus_state"
LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "signal_history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

latest_signals = []
signal_history = []
last_scan_time = None
scan_count = 0

HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NEXUS-AI v10</title>
  <style>
    body{margin:0;font-family:Arial,sans-serif;background:linear-gradient(180deg,#020814,#071325);color:#eef4ff}
    .app{max-width:760px;margin:0 auto;padding:14px}
    .hero,.section{background:#08182a;border:1px solid rgba(35,215,255,.12);border-radius:22px;padding:16px;margin-bottom:16px;box-shadow:0 8px 24px rgba(0,0,0,.28)}
    .hero-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
    .brand{display:flex;align-items:center;gap:12px}
    .logo{width:52px;height:52px;border-radius:16px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#7c4dff,#19f0d1);font-size:26px}
    .title{font-size:28px;font-weight:900;line-height:1}.title span{color:#19f0d1}
    .subtitle{margin-top:6px;font-size:12px;color:#91a4c3;letter-spacing:1.5px}
    .live{padding:10px 14px;border-radius:999px;background:rgba(20,60,50,.45);border:1px solid rgba(25,240,209,.24);color:#9bffe5;font-weight:bold;font-size:14px}
    .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
    .metric,.mini,.history-item,.asset-item,.stat-card{background:#0a1c30;border-radius:14px;padding:12px}
    .label{font-size:11px;color:#7e93b3;text-transform:uppercase;margin-bottom:6px}
    .value{font-size:18px;font-weight:bold}
    .tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}
    .tab-btn{padding:12px 8px;border:none;border-radius:14px;background:#0a1c30;color:#91a4c3;font-weight:bold;font-size:13px;cursor:pointer}
    .tab-btn.active{color:#19f0d1;outline:1px solid rgba(25,240,209,.25)}
    .panel{display:none}.panel.active{display:block}
    .section-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:18px;font-weight:bold}
    .muted{color:#91a4c3;font-size:13px;line-height:1.5}
    .signal-card{background:#0a1c30;border-radius:18px;padding:14px;margin-bottom:12px}
    .signal-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}
    .asset{font-size:21px;font-weight:bold}
    .badge{padding:8px 12px;border-radius:999px;font-size:13px;font-weight:bold}
    .call{background:linear-gradient(135deg,#19f0a0,#7dffc8);color:#062218}
    .put{background:linear-gradient(135deg,#ff7b8c,#ffc0c8);color:#311016}
    .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    .reason{margin-top:12px;background:#061321;border-radius:14px;padding:12px;white-space:pre-wrap;line-height:1.45;font-size:14px}
    .stats-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
    .history-list,.assets-list{display:flex;flex-direction:column;gap:10px}
    .history-top,.asset-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
    .rank{width:30px;height:30px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#8b5cf6,#22d3ee);font-weight:bold}
    .empty{text-align:center;padding:26px 12px;color:#91a4c3}
    .footer{text-align:center;color:#7e93b3;font-size:13px;margin-top:8px}
    @media(max-width:560px){.metrics{grid-template-columns:repeat(2,1fr)}.tabs{grid-template-columns:repeat(2,1fr)}.grid3{grid-template-columns:repeat(2,1fr)}.stats-grid{grid-template-columns:1fr}.title{font-size:24px}.asset{font-size:18px}}
  </style>
</head>
<body>
  <div class="app">
    <div class="hero">
      <div class="hero-top">
        <div class="brand">
          <div class="logo">⚡</div>
          <div>
            <div class="title">NEXUS-<span>AI</span> v10</div>
            <div class="subtitle">ULTRA ROBUSTA · BALANCEAMENTO DE APIS</div>
          </div>
        </div>
        <div class="live">● LIVE</div>
      </div>

      <div class="metrics">
        <div class="metric"><div class="label">Último scan</div><div class="value">{{ last_scan }}</div></div>
        <div class="metric"><div class="label">Scans</div><div class="value">{{ scan_count }}</div></div>
        <div class="metric"><div class="label">Sinais</div><div class="value">{{ signal_count }}</div></div>
        <div class="metric"><div class="label">Ativos</div><div class="value">{{ asset_count }}</div></div>
      </div>

      <div class="tabs">
        <button class="tab-btn active" onclick="showTab('signals', this)">⚡ SINAIS</button>
        <button class="tab-btn" onclick="showTab('history', this)">📋 HISTÓRICO</button>
        <button class="tab-btn" onclick="showTab('stats', this)">📊 STATS</button>
        <button class="tab-btn" onclick="showTab('assets', this)">🏆 ATIVOS</button>
      </div>
    </div>

    <div class="section">
      <div class="section-title">
        <div>Proteção e Balanceamento</div>
        <div class="muted">Binance · Finnhub · Twelve · Alpha</div>
      </div>

      <div class="muted">
        Twelve congelada hoje: <strong>{{ "SIM" if usage.twelve_frozen else "NÃO" }}</strong><br>
        Twelve pausa minuto: <strong>{{ "SIM" if usage.twelve_minute_paused else "NÃO" }}</strong><br>
        Finnhub congelada hoje: <strong>{{ "SIM" if usage.finnhub_frozen else "NÃO" }}</strong><br>
        Alpha congelada hoje: <strong>{{ "SIM" if usage.alpha_frozen else "NÃO" }}</strong><br>
        Chave Twelve 1 hoje: <strong>{{ usage.key1_daily }}</strong><br>
        Chave Twelve 2 hoje: <strong>{{ usage.key2_daily }}</strong>
      </div>
    </div>

    <div id="signals" class="section panel active">
      <div class="section-title">
        <div>Sinais em tempo real</div>
        <div class="muted">Sincronizados por arquivo</div>
      </div>

      {% if signals %}
        {% for s in signals %}
          <div class="signal-card">
            <div class="signal-head">
              <div class="asset">{{ s.asset }}</div>
              <div class="badge {% if s.signal == 'CALL' %}call{% else %}put{% endif %}">{{ s.signal }}</div>
            </div>

            <div class="grid3">
              <div class="mini"><div class="label">Score</div><div class="value">{{ s.score }}</div></div>
              <div class="mini"><div class="label">Confiança</div><div class="value">{{ s.confidence }}%</div></div>
              <div class="mini"><div class="label">Fonte</div><div class="value">{{ s.provider }}</div></div>
              <div class="mini"><div class="label">Timeframe</div><div class="value">{{ s.timeframe }}</div></div>
              <div class="mini"><div class="label">Entrada</div><div class="value">{{ s.entry_time }}</div></div>
              <div class="mini"><div class="label">Expiração</div><div class="value">{{ s.expiration }}</div></div>
            </div>

            <div class="reason">{{ s.reason_text }}</div>
          </div>
        {% endfor %}
      {% else %}
        <div class="empty">
          <div style="font-size:60px;">🔎</div>
          <div><strong>Nenhum sinal agora</strong></div>
        </div>
      {% endif %}
    </div>

    <div id="history" class="section panel">
      <div class="section-title"><div>Histórico</div><div class="muted">Últimos sinais</div></div>
      {% if history %}
        <div class="history-list">
          {% for h in history %}
            <div class="history-item">
              <div class="history-top">
                <div><strong>{{ h.asset }}</strong></div>
                <div class="badge {% if h.signal == 'CALL' %}call{% else %}put{% endif %}">{{ h.signal }}</div>
              </div>
              <div class="muted">
                Gerado: {{ h.generated_at }}<br>
                Score: {{ h.score }} · Fonte: {{ h.provider }}
              </div>
            </div>
          {% endfor %}
        </div>
      {% else %}
        <div class="empty">Sem histórico.</div>
      {% endif %}
    </div>

    <div id="stats" class="section panel">
      <div class="section-title"><div>Stats</div><div class="muted">Resumo</div></div>
      <div class="stats-grid">
        <div class="stat-card"><div class="label">Scans</div><div class="value">{{ scan_count }}</div></div>
        <div class="stat-card"><div class="label">Sinais</div><div class="value">{{ signal_count }}</div></div>
      </div>
    </div>

    <div id="assets" class="section panel">
      <div class="section-title"><div>Ativos</div><div class="muted">Monitorados</div></div>
      <div class="assets-list">
        {% for item in top_assets %}
          <div class="asset-item">
            <div class="asset-top">
              <div style="display:flex;align-items:center;gap:10px;">
                <div class="rank">{{ loop.index }}</div>
                <div><strong>{{ item }}</strong></div>
              </div>
              <div style="color:#1df2a4;font-weight:bold;">{{ providers_map.get(item, 'Auto') }}</div>
            </div>
          </div>
        {% endfor %}
      </div>
    </div>

    <div class="footer">Rotas: /health · /signals · /usage</div>
  </div>

  <script>
    function showTab(tabId, btn){
      document.querySelectorAll('.panel').forEach(function(p){ p.classList.remove('active'); });
      document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
      document.getElementById(tabId).classList.add('active');
      btn.classList.add('active');
    }
  </script>
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
            "entry_time": str(s.get("entry_time", "--:--")),
            "expiration": str(s.get("expiration", "Próximo candle")),
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

@app.route("/")
def home():
    signals, history, meta = load_state()
    usage = data_manager.get_usage_snapshot()

    providers_map = {}
    for symbol in ASSETS[:8]:
        providers_map[symbol] = data_manager.last_provider_used.get(symbol, "Auto")

    template_usage = {
        "twelve_frozen": usage.get("twelve_frozen", False),
        "twelve_minute_paused": usage.get("twelve_minute_paused", False),
        "finnhub_frozen": usage.get("finnhub_frozen", False),
        "alpha_frozen": usage.get("alpha_frozen", False),
        "key1_daily": usage.get("keys", [{}])[0].get("daily_used", 0) if len(usage.get("keys", [])) > 0 else 0,
        "key2_daily": usage.get("keys", [{}, {}])[1].get("daily_used", 0) if len(usage.get("keys", [])) > 1 else 0,
    }

    return render_template_string(
        HTML_PAGE,
        signals=signals,
        history=history[:10],
        last_scan=meta.get("last_scan", "--"),
        scan_count=meta.get("scan_count", 0),
        signal_count=len(signals),
        asset_count=len(ASSETS),
        top_assets=ASSETS[:8],
        providers_map=providers_map,
        usage=template_usage
    )

@app.route("/health")
def health():
    return {"status": "NEXUS v10 sync running"}

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
    app.run(host="0.0.0.0", port=10000)
