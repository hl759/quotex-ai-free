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
from decision_engine import DecisionEngine
from config import ASSETS, SCAN_INTERVAL_SECONDS

app = Flask(__name__)

data_manager = DataManager()
learning = LearningEngine()
scanner = MarketScanner(data_manager, learning)
signal_engine = SignalEngine(learning)
decision_engine = DecisionEngine(learning)
result_evaluator = ResultEvaluator()
journal = JournalManager()

STATE_DIR = "/tmp/nexus_state"
LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")
CURRENT_DECISION_FILE = os.path.join(STATE_DIR, "current_decision.json")

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

def normalize_signals(signals):
    out = []
    for s in signals:
        analysis = now_brazil()
        entry = analysis + timedelta(minutes=1)
        expiration = entry + timedelta(minutes=1)
        reason = s.get("reason", [])
        if isinstance(reason, list):
            reason_text = "\n".join(["• " + str(r) for r in reason]) if reason else "Sem detalhes"
        else:
            reason_text = str(reason)
        out.append({
            "asset": s.get("asset", "N/A"),
            "signal": s.get("signal", "CALL"),
            "score": s.get("score", 0),
            "confidence": s.get("confidence", 50),
            "confidence_label": s.get("confidence_label", "MÉDIO"),
            "provider": s.get("provider", "auto"),
            "analysis_time": analysis.strftime("%H:%M"),
            "entry_time": entry.strftime("%H:%M"),
            "expiration": expiration.strftime("%H:%M"),
            "reason_text": reason_text,
            "regime": s.get("regime", "unknown")
        })
    return out

def decorate_decision(decision):
    analysis = now_brazil()
    entry = analysis + timedelta(minutes=1)
    expiration = entry + timedelta(minutes=1)
    reasons = decision.get("reasons", [])
    if isinstance(reasons, list):
        reason_text = "\n".join(["• " + str(r) for r in reasons]) if reasons else "Sem detalhes"
    else:
        reason_text = str(reasons)
    return {
        "asset": decision.get("asset", "MERCADO"),
        "decision": decision.get("decision", "NAO_OPERAR"),
        "direction": decision.get("direction"),
        "score": decision.get("score", 0),
        "confidence": decision.get("confidence", 50),
        "regime": decision.get("regime", "unknown"),
        "analysis_time": analysis.strftime("%H:%M"),
        "entry_time": entry.strftime("%H:%M"),
        "expiration": expiration.strftime("%H:%M"),
        "reason_text": reason_text
    }

def save_state(signals, history, current_decision, scans):
    write_json(LATEST_SIGNALS_FILE, signals)
    write_json(SIGNAL_HISTORY_FILE, history[:50])
    write_json(CURRENT_DECISION_FILE, current_decision)
    write_json(META_FILE, {"last_scan": now_brazil().strftime("%H:%M:%S"), "scan_count": scans})

def load_state():
    signals = read_json(LATEST_SIGNALS_FILE, [])
    history = read_json(SIGNAL_HISTORY_FILE, [])
    current_decision = read_json(CURRENT_DECISION_FILE, {})
    meta = read_json(META_FILE, {"last_scan": "--", "scan_count": 0})
    return signals, history, current_decision, meta

def get_snapshot():
    signals, history, current_decision, meta = load_state()
    return {
        "signals": signals,
        "history": history[:20],
        "current_decision": current_decision,
        "meta": {
            "last_scan": meta.get("last_scan", "--"),
            "scan_count": meta.get("scan_count", 0),
            "signal_count": len(signals),
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
            raw_signals = signal_engine.generate_signals(market)
            signals = normalize_signals(raw_signals if raw_signals else [])

            decision_candidates = []
            for item in market:
                decision = decision_engine.decide(item.get("asset"), item.get("indicators", {}))
                decision["provider"] = item.get("provider", "auto")
                decision_candidates.append((decision, item))

            if decision_candidates:
                decision_candidates.sort(key=lambda x: (x[0].get("score", 0), x[0].get("confidence", 0)), reverse=True)
                best_decision_raw, _ = decision_candidates[0]
            else:
                best_decision_raw = {
                    "asset": "MERCADO",
                    "decision": "NAO_OPERAR",
                    "direction": None,
                    "score": 0,
                    "confidence": 50,
                    "regime": "unknown",
                    "reasons": ["Sem dados suficientes no momento"]
                }

            current_decision = decorate_decision(best_decision_raw)

            if raw_signals:
                for idx, signal in enumerate(raw_signals):
                    matched_asset = next((item for item in market if item.get("asset") == signal.get("asset")), None)
                    if matched_asset:
                        result_data = result_evaluator.evaluate(signal, matched_asset.get("candles", []))
                        if result_data:
                            safe_signal = dict(signal)
                            if idx < len(signals):
                                safe_signal["analysis_time"] = signals[idx]["analysis_time"]
                                safe_signal["entry_time"] = signals[idx]["entry_time"]
                                safe_signal["expiration"] = signals[idx]["expiration"]
                            learning.register_result(safe_signal, result_data)

            history = read_json(SIGNAL_HISTORY_FILE, [])
            if signals:
                history = signals + history

            scan_count += 1
            save_state(signals, history, current_decision, scan_count)

            print(f"Scan #{scan_count} | Signals: {len(signals)} | Decision: {current_decision['decision']} | Asset: {current_decision['asset']}", flush=True)
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

HTML_PAGE = """
<!DOCTYPE html>
<html lang='pt-BR'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>NEXUS AI v10.7 • Regime Inteligente</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:linear-gradient(180deg,#04101d 0%,#07192e 100%);color:#eef6ff}
.app{max-width:780px;margin:0 auto;padding:18px}
.hero,.card{background:linear-gradient(180deg,#0a1d33 0%,#0b2340 100%);border:1px solid rgba(80,220,255,.10);border-radius:28px;padding:18px;margin-bottom:18px;box-shadow:0 12px 40px rgba(0,0,0,.28)}
.hero-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:62px;height:62px;border-radius:18px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#6c63ff,#24e5c2);font-size:34px}
.title{font-size:30px;font-weight:900}.title .ai{color:#25e6c4}.subtitle{color:#8fa7c4;margin-top:8px;font-size:13px;letter-spacing:1.8px}
.right-box{display:flex;flex-direction:column;gap:10px}.live{min-width:110px;text-align:center;padding:16px 14px;border-radius:999px;border:1px solid rgba(37,230,196,.24);background:rgba(14,54,55,.45);color:#86ffe8;font-size:18px;font-weight:800}.refresh-btn{border:none;border-radius:999px;padding:12px 16px;background:linear-gradient(180deg,#103153 0%,#153d66 100%);color:#25e6c4;font-size:14px;font-weight:800;cursor:pointer}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-top:18px}.metric{background:#132b49;border-radius:18px;padding:18px}.metric-label,.section-sub,.mini-label,.muted{color:#8fa7c4}.metric-value{font-size:24px;font-weight:800}
.tabs{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:18px}.tab-btn{border:none;border-radius:18px;padding:16px 10px;background:#132b49;color:#a8bdd8;font-size:14px;font-weight:800;cursor:pointer}.tab-btn.active{background:linear-gradient(180deg,#103153 0%,#153d66 100%);color:#25e6c4}
.section-title{font-size:17px;font-weight:800;margin-bottom:8px}.status-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.status-item,.signal-card,.list-card,.decision-card{background:#132b49;border-radius:18px;padding:14px;margin-top:12px}
.signal-head,.decision-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.asset{font-size:22px;font-weight:900}
.badge{padding:9px 14px;border-radius:999px;font-size:13px;font-weight:900}.call{background:linear-gradient(135deg,#25e6a0,#8affcc);color:#053324}.put{background:linear-gradient(135deg,#ff7a8a,#ffc0c8);color:#3f1119}.hold{background:linear-gradient(135deg,#8c95a6,#d2d7df);color:#20242b}
.signal-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.mini{background:#0f223a;border-radius:14px;padding:12px}.mini-value{font-size:18px;font-weight:800}.reason{margin-top:14px;background:#0d1c31;border-radius:14px;padding:14px;color:#bdd0e8;line-height:1.6;white-space:normal}
.empty{text-align:center;color:#9bb2cf;padding:26px 10px}.panel{display:none}.panel.active{display:block}.list-title{font-size:18px;font-weight:800;margin-bottom:6px}
@media(max-width:640px){.tabs{grid-template-columns:repeat(2,1fr)}.hero-top{align-items:flex-start}.right-box{min-width:120px}}
</style>
</head>
<body>
<div class='app'>
<div class='hero'>
<div class='hero-top'>
<div class='brand'><div class='logo'>⚡</div><div><div class='title'>NEXUS <span class='ai'>AI</span> v10.7</div><div class='subtitle'>REGIME INTELIGENTE • VISUAL CORRIGIDO</div></div></div>
<div class='right-box'><div class='live'>● LIVE</div><button id='refreshBtn' class='refresh-btn' onclick='refreshSnapshot()'>↻ Atualizar agora</button></div>
</div>
<div class='metrics'>
<div class='metric'><div class='metric-label'>Último scan</div><div class='metric-value' id='last_scan'></div></div>
<div class='metric'><div class='metric-label'>Scans</div><div class='metric-value' id='scan_count'></div></div>
<div class='metric'><div class='metric-label'>Sinais</div><div class='metric-value' id='signal_count'></div></div>
<div class='metric'><div class='metric-label'>Ativos</div><div class='metric-value' id='asset_count'></div></div>
</div>
<div class='tabs'>
<button class='tab-btn active' onclick="showTab('signals', this)">⚡ Sinais</button>
<button class='tab-btn' onclick="showTab('decision', this)">🧠 Decisão</button>
<button class='tab-btn' onclick="showTab('history', this)">📋 Histórico</button>
<button class='tab-btn' onclick="showTab('stats', this)">📊 Stats</button>
<button class='tab-btn' onclick="showTab('assets', this)">🏆 Ativos</button>
<button class='tab-btn' onclick="showTab('hours', this)">⏰ Horários</button>
</div>
</div>
<div id='signals' class='panel active'><div class='card'><div class='section-title'>Sinais atuais</div><div class='section-sub'>Fluxo original preservado</div><div id='signals_container'></div></div></div>
<div id='decision' class='panel'><div class='card'><div class='section-title'>Decisão do momento</div><div class='section-sub'>Regime inteligente com visual corrigido</div><div id='decision_container'></div></div></div>
<div id='history' class='panel'><div class='card'><div class='section-title'>Histórico recente</div><div class='section-sub'>Últimos sinais salvos</div><div id='history_container'></div></div></div>
<div id='stats' class='panel'><div class='card'><div class='section-title'>Aprendizado</div><div class='section-sub'>Acompanhamento do motor adaptativo</div><div class='status-grid'><div class='status-item'>Total avaliadas<br><b id='stats_total'></b></div><div class='status-item'>Win rate<br><b id='stats_winrate'></b></div><div class='status-item'>Wins<br><b id='stats_wins'></b></div><div class='status-item'>Loss<br><b id='stats_loss'></b></div></div></div></div>
<div id='assets' class='panel'><div class='card'><div class='section-title'>Melhores ativos</div><div class='section-sub'>Ranking baseado no histórico avaliado</div><div id='assets_container'></div></div></div>
<div id='hours' class='panel'><div class='card'><div class='section-title'>Melhores horários</div><div class='section-sub'>Ranking por faixa horária</div><div id='hours_container'></div></div></div>
</div>
<script>
const initialSnapshot = {{ snapshot_json|safe }};
function showTab(tabId, btn){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));document.getElementById(tabId).classList.add('active');btn.classList.add('active');}
function escapeHtml(text){if(text===null||text===undefined)return "";return String(text).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");}
function formatText(text){return escapeHtml(text).replaceAll("\\n","<br>");}
function renderSignals(signals){const c=document.getElementById("signals_container");if(!signals||signals.length===0){c.innerHTML='<div class="empty">Nenhum sinal disponível agora.</div>';return;}let h="";signals.forEach(s=>{const bc=s.signal==="CALL"?"call":"put";h+=`<div class="signal-card"><div class="signal-head"><div class="asset">${escapeHtml(s.asset)}</div><div class="badge ${bc}">${escapeHtml(s.signal)}${s.confidence_label ? " • " + escapeHtml(s.confidence_label) : ""}</div></div><div class="signal-grid"><div class="mini"><div class="mini-label">Score</div><div class="mini-value">${escapeHtml(s.score)}</div></div><div class="mini"><div class="mini-label">Confiança</div><div class="mini-value">${escapeHtml(s.confidence)}%</div></div><div class="mini"><div class="mini-label">Análise</div><div class="mini-value">${escapeHtml(s.analysis_time)}</div></div><div class="mini"><div class="mini-label">Entrada</div><div class="mini-value">${escapeHtml(s.entry_time)}</div></div><div class="mini"><div class="mini-label">Expiração</div><div class="mini-value">${escapeHtml(s.expiration)}</div></div><div class="mini"><div class="mini-label">Regime</div><div class="mini-value">${escapeHtml(s.regime)}</div></div></div><div class="reason">${formatText(s.reason_text)}</div></div>`});c.innerHTML=h;}
function renderDecision(d){const c=document.getElementById("decision_container");if(!d||!d.decision){c.innerHTML='<div class="empty">Sem decisão disponível agora.</div>';return;}let badgeClass="hold";let badgeText=d.decision;if(d.direction==="CALL") badgeClass="call"; else if(d.direction==="PUT") badgeClass="put"; if(d.decision==="NAO_OPERAR") badgeText="NÃO OPERAR"; else if(d.decision==="ENTRADA_FORTE") badgeText=(d.direction||"CALL")+" • FORTE"; else if(d.decision==="ENTRADA_CAUTELA") badgeText=(d.direction||"CALL")+" • CAUTELA"; c.innerHTML=`<div class="decision-card"><div class="decision-head"><div class="asset">${escapeHtml(d.asset||"MERCADO")}</div><div class="badge ${badgeClass}">${escapeHtml(badgeText)}</div></div><div class="signal-grid"><div class="mini"><div class="mini-label">Score</div><div class="mini-value">${escapeHtml(d.score)}</div></div><div class="mini"><div class="mini-label">Confiança</div><div class="mini-value">${escapeHtml(d.confidence)}%</div></div><div class="mini"><div class="mini-label">Análise</div><div class="mini-value">${escapeHtml(d.analysis_time)}</div></div><div class="mini"><div class="mini-label">Entrada</div><div class="mini-value">${escapeHtml(d.entry_time)}</div></div><div class="mini"><div class="mini-label">Expiração</div><div class="mini-value">${escapeHtml(d.expiration)}</div></div><div class="mini"><div class="mini-label">Regime</div><div class="mini-value">${escapeHtml(d.regime)}</div></div></div><div class="reason">${formatText(d.reason_text)}</div></div>`;}
function renderHistory(history){const c=document.getElementById("history_container");if(!history||history.length===0){c.innerHTML='<div class="empty">Ainda não há histórico salvo.</div>';return;}let h="";history.forEach(x=>{h+=`<div class="list-card"><div class="list-title">${escapeHtml(x.asset)} • ${escapeHtml(x.signal)}</div><div class="muted">Análise: ${escapeHtml(x.analysis_time)}<br>Entrada: ${escapeHtml(x.entry_time)}<br>Expiração: ${escapeHtml(x.expiration)}<br>Score: ${escapeHtml(x.score)} • Confiança: ${escapeHtml(x.confidence)}% • Fonte: ${escapeHtml(x.provider)}</div></div>`});c.innerHTML=h;}
function renderBestAssets(bestAssets){const c=document.getElementById("assets_container");if(!bestAssets||bestAssets.length===0){c.innerHTML='<div class="empty">Ainda sem dados suficientes.</div>';return;}let h="";bestAssets.forEach(x=>{h+=`<div class="list-card"><div class="list-title">${escapeHtml(x.asset)}</div><div class="muted">Win rate: <b>${escapeHtml(x.winrate)}%</b><br>Trades: <b>${escapeHtml(x.total)}</b><br>Wins: <b>${escapeHtml(x.wins)}</b></div></div>`});c.innerHTML=h;}
function renderBestHours(bestHours){const c=document.getElementById("hours_container");if(!bestHours||bestHours.length===0){c.innerHTML='<div class="empty">Ainda sem dados suficientes.</div>';return;}let h="";bestHours.forEach(x=>{h+=`<div class="list-card"><div class="list-title">${escapeHtml(x.hour)}</div><div class="muted">Win rate: <b>${escapeHtml(x.winrate)}%</b><br>Trades: <b>${escapeHtml(x.total)}</b><br>Wins: <b>${escapeHtml(x.wins)}</b></div></div>`});c.innerHTML=h;}
function applySnapshot(d){document.getElementById("last_scan").textContent=d.meta.last_scan;document.getElementById("scan_count").textContent=d.meta.scan_count;document.getElementById("signal_count").textContent=d.meta.signal_count;document.getElementById("asset_count").textContent=d.meta.asset_count;document.getElementById("stats_total").textContent=d.learning_stats.total;document.getElementById("stats_winrate").textContent=d.learning_stats.winrate + "%";document.getElementById("stats_wins").textContent=d.learning_stats.wins;document.getElementById("stats_loss").textContent=d.learning_stats.loss;renderSignals(d.signals);renderDecision(d.current_decision);renderHistory(d.history);renderBestAssets(d.best_assets);renderBestHours(d.best_hours);}
async function refreshSnapshot(){const btn=document.getElementById("refreshBtn");btn.disabled=true;btn.textContent="Atualizando...";try{const r=await fetch("/snapshot",{cache:"no-store"});const d=await r.json();applySnapshot(d);btn.textContent="✓ Atualizado";}catch(e){btn.textContent="Erro ao atualizar";}setTimeout(()=>{btn.disabled=false;btn.textContent="↻ Atualizar agora";},1200);}
applySnapshot(initialSnapshot);
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
    return render_template_string(HTML_PAGE, snapshot_json=json.dumps(get_snapshot(), ensure_ascii=False))

@app.route("/health")
def health():
    ensure_scanner_started()
    return {"status": "running"}

@app.route("/snapshot")
def snapshot():
    ensure_scanner_started()
    return jsonify(get_snapshot())

if __name__ == "__main__":
    ensure_scanner_started()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
