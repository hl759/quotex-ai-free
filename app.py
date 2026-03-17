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
# MOTORES
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
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")

os.makedirs(STATE_DIR, exist_ok=True)

scan_count = 0
last_scan_time = None
scanner_started = False
scanner_lock = threading.Lock()


# =========================
# UTIL
# =========================
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

        reason = s.get("reason", [])
        if isinstance(reason, list):
            reason_text = "\n".join(["• " + str(r) for r in reason]) if reason else "Sem detalhes"
        else:
            reason_text = str(reason)

        normalized.append({
            "asset": s.get("asset", "N/A"),
            "signal": s.get("signal", "CALL"),
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


# =========================
# LOOP ESTÁVEL
# =========================
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
            last_scan_time = now_brazil()

            save_state(signals, history, last_scan_time, scan_count)

            print("Scan #%s | Signals: %s" % (scan_count, len(signals)), flush=True)

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


# =========================
# LAYOUT PREMIUM
# =========================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEXUS AI v10.1</title>
<style>
    *{box-sizing:border-box}
    body{
        margin:0;
        font-family:Arial,sans-serif;
        background:linear-gradient(180deg,#04101d 0%, #07192e 100%);
        color:#eef6ff;
    }
    .app{
        max-width:780px;
        margin:0 auto;
        padding:18px;
    }
    .hero,.card{
        background:linear-gradient(180deg,#0a1d33 0%, #0b2340 100%);
        border:1px solid rgba(80,220,255,.10);
        border-radius:28px;
        padding:18px;
        margin-bottom:18px;
        box-shadow:0 12px 40px rgba(0,0,0,.28);
    }
    .hero-top{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px;
    }
    .brand{
        display:flex;
        align-items:center;
        gap:14px;
    }
    .logo{
        width:62px;
        height:62px;
        border-radius:18px;
        display:flex;
        align-items:center;
        justify-content:center;
        background:linear-gradient(135deg,#6c63ff,#24e5c2);
        font-size:34px;
        box-shadow:0 8px 24px rgba(0,0,0,.25);
    }
    .title{
        font-size:30px;
        font-weight:900;
        line-height:1;
        letter-spacing:.5px;
    }
    .title .ai{
        color:#25e6c4;
    }
    .subtitle{
        color:#8fa7c4;
        margin-top:8px;
        font-size:13px;
        letter-spacing:1.8px;
    }
    .live{
        min-width:110px;
        text-align:center;
        padding:16px 14px;
        border-radius:999px;
        border:1px solid rgba(37,230,196,.24);
        background:rgba(14,54,55,.45);
        color:#86ffe8;
        font-size:18px;
        font-weight:800;
        box-shadow:0 0 20px rgba(37,230,196,.08) inset;
    }
    .metrics{
        display:grid;
        grid-template-columns:repeat(2,1fr);
        gap:14px;
        margin-top:18px;
    }
    .metric{
        background:#132b49;
        border-radius:18px;
        padding:18px;
    }
    .metric-label{
        color:#8fa7c4;
        font-size:13px;
        margin-bottom:10px;
    }
    .metric-value{
        font-size:24px;
        font-weight:800;
    }
    .tabs{
        display:grid;
        grid-template-columns:repeat(4,1fr);
        gap:12px;
        margin-top:18px;
    }
    .tab-btn{
        border:none;
        border-radius:18px;
        padding:16px 10px;
        background:#132b49;
        color:#a8bdd8;
        font-size:14px;
        font-weight:800;
        cursor:pointer;
    }
    .tab-btn.active{
        background:linear-gradient(180deg,#103153 0%, #153d66 100%);
        color:#25e6c4;
        box-shadow:0 0 0 1px rgba(37,230,196,.18) inset;
    }
    .section-title{
        font-size:17px;
        font-weight:800;
        margin-bottom:8px;
    }
    .section-sub{
        color:#8fa7c4;
        font-size:13px;
        margin-bottom:14px;
    }
    .status-grid{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:12px;
    }
    .status-item{
        background:#132b49;
        border-radius:16px;
        padding:14px;
    }
    .status-item b{
        color:#ffffff;
    }
    .signal-card{
        background:#132b49;
        border-radius:20px;
        padding:16px;
        margin-top:12px;
    }
    .signal-head{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px;
        margin-bottom:12px;
    }
    .asset{
        font-size:22px;
        font-weight:900;
    }
    .badge{
        padding:9px 14px;
        border-radius:999px;
        font-size:13px;
        font-weight:900;
    }
    .call{
        background:linear-gradient(135deg,#25e6a0,#8affcc);
        color:#053324;
    }
    .put{
        background:linear-gradient(135deg,#ff7a8a,#ffc0c8);
        color:#3f1119;
    }
    .signal-grid{
        display:grid;
        grid-template-columns:repeat(2,1fr);
        gap:12px;
    }
    .mini{
        background:#0f223a;
        border-radius:14px;
        padding:12px;
    }
    .mini-label{
        color:#8fa7c4;
        font-size:12px;
        margin-bottom:6px;
    }
    .mini-value{
        font-size:18px;
        font-weight:800;
    }
    .reason{
        margin-top:14px;
        background:#0d1c31;
        border-radius:14px;
        padding:14px;
        color:#bdd0e8;
        line-height:1.5;
        white-space:pre-wrap;
    }
    .empty{
        text-align:center;
        color:#9bb2cf;
        padding:26px 10px;
    }
    .panel{
        display:none;
    }
    .panel.active{
        display:block;
    }
    .list-card{
        background:#132b49;
        border-radius:18px;
        padding:14px;
        margin-top:12px;
    }
    .list-title{
        font-size:18px;
        font-weight:800;
        margin-bottom:6px;
    }
    .muted{
        color:#9bb2cf;
        line-height:1.5;
    }
    @media(max-width:640px){
        .tabs{
            grid-template-columns:repeat(2,1fr);
        }
    }
</style>
</head>
<body>
<div class="app">

    <div class="hero">
        <div class="hero-top">
            <div class="brand">
                <div class="logo">⚡</div>
                <div>
                    <div class="title">NEXUS <span class="ai">AI</span> v10.1</div>
                    <div class="subtitle">ULTRA ROBUSTA • AUTO LEARNING</div>
                </div>
            </div>
            <div class="live">● LIVE</div>
        </div>

        <div class="metrics">
            <div class="metric">
                <div class="metric-label">Último scan</div>
                <div class="metric-value">{{ last_scan }}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Scans</div>
                <div class="metric-value">{{ scan_count }}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Sinais</div>
                <div class="metric-value">{{ signal_count }}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Ativos</div>
                <div class="metric-value">{{ asset_count }}</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="showTab('signals', this)">⚡ Sinais</button>
            <button class="tab-btn" onclick="showTab('history', this)">📋 Histórico</button>
            <button class="tab-btn" onclick="showTab('stats', this)">📊 Stats</button>
            <button class="tab-btn" onclick="showTab('assets', this)">🏆 Ativos</button>
        </div>
    </div>

    <div id="signals" class="panel active">
        <div class="card">
            <div class="section-title">Sinais atuais</div>
            <div class="section-sub">Entrada 1 minuto após a análise</div>

            {% if signals %}
                {% for s in signals %}
                <div class="signal-card">
                    <div class="signal-head">
                        <div class="asset">{{ s.asset }}</div>
                        {% if s.signal == "CALL" %}
                            <div class="badge call">CALL</div>
                        {% else %}
                            <div class="badge put">PUT</div>
                        {% endif %}
                    </div>

                    <div class="signal-grid">
                        <div class="mini">
                            <div class="mini-label">Score</div>
                            <div class="mini-value">{{ s.score }}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Confiança</div>
                            <div class="mini-value">{{ s.confidence }}%</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Análise</div>
                            <div class="mini-value">{{ s.analysis_time }}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Entrada</div>
                            <div class="mini-value">{{ s.entry_time }}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Expiração</div>
                            <div class="mini-value">{{ s.expiration }}</div>
                        </div>
                        <div class="mini">
                            <div class="mini-label">Fonte</div>
                            <div class="mini-value">{{ s.provider }}</div>
                        </div>
                    </div>

                    <div class="reason">{{ s.reason_text }}</div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty">Nenhum sinal disponível agora.</div>
            {% endif %}
        </div>
    </div>

    <div id="history" class="panel">
        <div class="card">
            <div class="section-title">Histórico recente</div>
            <div class="section-sub">Últimos sinais salvos</div>

            {% if history %}
                {% for h in history %}
                <div class="list-card">
                    <div class="list-title">{{ h.asset }} • {{ h.signal }}</div>
                    <div class="muted">
                        Análise: {{ h.analysis_time }}<br>
                        Entrada: {{ h.entry_time }}<br>
                        Expiração: {{ h.expiration }}<br>
                        Score: {{ h.score }} • Confiança: {{ h.confidence }}% • Fonte: {{ h.provider }}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty">Ainda não há histórico salvo.</div>
            {% endif %}
        </div>
    </div>

    <div id="stats" class="panel">
        <div class="card">
            <div class="section-title">Aprendizado</div>
            <div class="section-sub">Acompanhamento do motor adaptativo</div>

            <div class="status-grid">
                <div class="status-item">Total avaliadas<br><b>{{ learning_stats.total }}</b></div>
                <div class="status-item">Win rate<br><b>{{ learning_stats.winrate }}%</b></div>
                <div class="status-item">Wins<br><b>{{ learning_stats.wins }}</b></div>
                <div class="status-item">Loss<br><b>{{ learning_stats.loss }}</b></div>
            </div>
        </div>
    </div>

    <div id="assets" class="panel">
        <div class="card">
            <div class="section-title">Melhores ativos</div>
            <div class="section-sub">Ranking baseado no histórico avaliado</div>

            {% if best_assets %}
                {% for item in best_assets %}
                <div class="list-card">
                    <div class="list-title">{{ item.asset }}</div>
                    <div class="muted">
                        Win rate: <b>{{ item.winrate }}%</b><br>
                        Trades: <b>{{ item.total }}</b><br>
                        Wins: <b>{{ item.wins }}</b>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty">Ainda sem dados suficientes.</div>
            {% endif %}
        </div>
    </div>

</div>

<script>
function showTab(tabId, btn){
    document.querySelectorAll('.panel').forEach(function(panel){
        panel.classList.remove('active');
    });

    document.querySelectorAll('.tab-btn').forEach(function(button){
        button.classList.remove('active');
    });

    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
}
</script>
</body>
</html>
"""


@app.before_request
def _boot():
    ensure_scanner_started()


@app.route("/")
def home():
    ensure_scanner_started()

    signals, history, meta = load_state()
    learning_stats = journal.stats()
    best_assets = journal.best_assets()

    return render_template_string(
        HTML_PAGE,
        signals=signals,
        history=history[:20],
        last_scan=meta.get("last_scan", "--"),
        scan_count=meta.get("scan_count", 0),
        signal_count=len(signals),
        asset_count=len(ASSETS),
        learning_stats=learning_stats,
        best_assets=best_assets
    )


@app.route("/health")
def health():
    ensure_scanner_started()
    return {"status": "running"}


@app.route("/signals")
def signals():
    ensure_scanner_started()
    signals, _, _ = load_state()
    return jsonify(signals)


@app.route("/history")
def history():
    ensure_scanner_started()
    _, history, _ = load_state()
    return jsonify(history)


@app.route("/learning-stats")
def learning_stats():
    ensure_scanner_started()
    return jsonify(journal.stats())


@app.route("/best-assets")
def best_assets():
    ensure_scanner_started()
    return jsonify(journal.best_assets())


if __name__ == "__main__":
    ensure_scanner_started()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
