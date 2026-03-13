from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import requests
import numpy as np
import time
import threading
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")

ASSETS = [
    # Forex Major (8 pares)
    {"symbol": "EUR/USD", "type": "forex"},
    {"symbol": "GBP/USD", "type": "forex"},
    {"symbol": "USD/JPY", "type": "forex"},
    {"symbol": "AUD/USD", "type": "forex"},
    {"symbol": "USD/CAD", "type": "forex"},
    {"symbol": "USD/CHF", "type": "forex"},
    {"symbol": "NZD/USD", "type": "forex"},
    {"symbol": "EUR/GBP", "type": "forex"},
    # Forex Cross (6 pares)
    {"symbol": "GBP/JPY", "type": "forex"},
    {"symbol": "EUR/JPY", "type": "forex"},
    {"symbol": "EUR/CHF", "type": "forex"},
    {"symbol": "AUD/JPY", "type": "forex"},
    {"symbol": "GBP/CHF", "type": "forex"},
    {"symbol": "CAD/JPY", "type": "forex"},
    # Cripto (6 pares)
    {"symbol": "BTC/USD", "type": "crypto"},
    {"symbol": "ETH/USD", "type": "crypto"},
    {"symbol": "LTC/USD", "type": "crypto"},
    {"symbol": "XRP/USD", "type": "crypto"},
    {"symbol": "ADA/USD", "type": "crypto"},
    {"symbol": "SOL/USD", "type": "crypto"},
]

state = {
    "signals": [],
    "last_scan": None,
    "scan_count": 0,
    "scanning": False,
}

def fetch_candles(symbol, interval="5min", outputsize=60):
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_DATA_KEY,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if "values" not in data:
            return None
        candles = []
        for v in reversed(data["values"]):
            candles.append({
                "open": float(v["open"]),
                "high": float(v["high"]),
                "low": float(v["low"]),
                "close": float(v["close"]),
                "volume": float(v.get("volume", 1)),
                "time": v["datetime"],
            })
        return candles
    except Exception as e:
        print(f"Erro {symbol}: {e}")
        return None

def ema(closes, period):
    if len(closes) < period:
        return float(closes[-1])
    alpha = 2.0 / (period + 1)
    val = float(closes[0])
    for c in closes[1:]:
        val = alpha * float(c) + (1 - alpha) * val
    return val

def rsi_calc(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    closes = [float(c) for c in closes]
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period-1) + gains[i]) / period
        avg_loss = (avg_loss * (period-1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def detect_pattern(candles):
    if len(candles) < 2:
        return None, 0
    c = candles
    body = abs(c[-1]["close"] - c[-1]["open"])
    rng = c[-1]["high"] - c[-1]["low"]
    if rng == 0:
        return None, 0
    upper_wick = c[-1]["high"] - max(c[-1]["close"], c[-1]["open"])
    lower_wick = min(c[-1]["close"], c[-1]["open"]) - c[-1]["low"]

    if (c[-2]["close"] < c[-2]["open"] and c[-1]["close"] > c[-1]["open"] and
            c[-1]["open"] < c[-2]["close"] and c[-1]["close"] > c[-2]["open"]):
        return "BULLISH ENGULFING", 1

    if (c[-2]["close"] > c[-2]["open"] and c[-1]["close"] < c[-1]["open"] and
            c[-1]["open"] > c[-2]["close"] and c[-1]["close"] < c[-2]["open"]):
        return "BEARISH ENGULFING", -1

    if lower_wick > body * 2 and upper_wick < body * 0.5 and body > 0:
        return "HAMMER", 1

    if upper_wick > body * 2 and lower_wick < body * 0.5 and body > 0:
        return "SHOOTING STAR", -1

    if lower_wick > rng * 0.6:
        return "BULLISH PIN BAR", 1

    if upper_wick > rng * 0.6:
        return "BEARISH PIN BAR", -1

    return None, 0

def analyze_asset(symbol, candles_m5, candles_m1):
    if not candles_m5 or not candles_m1:
        return None
    if len(candles_m5) < 30 or len(candles_m1) < 30:
        return None

    closes_m5 = [c["close"] for c in candles_m5]
    closes_m1 = [c["close"] for c in candles_m1]
    current = closes_m5[-1]

    e9_m5  = ema(closes_m5, 9)
    e21_m5 = ema(closes_m5, 21)
    e50_m5 = ema(closes_m5, min(50, len(closes_m5)-1))
    e9_m1  = ema(closes_m1, 9)
    e21_m1 = ema(closes_m1, 21)

    rsi_m5 = rsi_calc(closes_m5)
    rsi_m1 = rsi_calc(closes_m1)

    trend_m5 = 1 if e9_m5 > e21_m5 > e50_m5 else (-1 if e9_m5 < e21_m5 < e50_m5 else 0)
    trend_m1 = 1 if e9_m1 > e21_m1 else (-1 if e9_m1 < e21_m1 else 0)

    if trend_m5 == 0 or trend_m1 == 0 or trend_m5 != trend_m1:
        return None

    direction = trend_m5

    if 45 <= rsi_m5 <= 55:
        return None

    pattern_name, pattern_dir = detect_pattern(candles_m1[-5:])
    if not pattern_name or pattern_dir != direction:
        return None

    score = 0.0
    explanation = []

    if direction == 1 and e9_m5 > e21_m5 > e50_m5:
        score += 2.0
        explanation.append("✓ EMA bullish stack M5 (9>21>50)")
    elif direction == -1 and e9_m5 < e21_m5 < e50_m5:
        score += 2.0
        explanation.append("✓ EMA bearish stack M5 (9<21<50)")
    else:
        score += 1.0

    if direction == 1 and rsi_m5 < 42:
        score += 1.0
        explanation.append(f"✓ RSI sobrevendido {rsi_m5:.1f}")
    elif direction == -1 and rsi_m5 > 58:
        score += 1.0
        explanation.append(f"✓ RSI sobrecomprado {rsi_m5:.1f}")
    else:
        score += 0.5
        explanation.append(f"✓ RSI favorável {rsi_m5:.1f}")

    score += 1.5
    explanation.append(f"✓ Padrão: {pattern_name}")

    highs = [c["high"] for c in candles_m5[-20:]]
    lows  = [c["low"]  for c in candles_m5[-20:]]
    avg_range = sum(h - l for h, l in zip(highs, lows)) / len(highs)

    if direction == 1 and (current - min(lows)) < avg_range * 1.5:
        score += 1.5
        explanation.append("✓ Próximo ao suporte")
    elif direction == -1 and (max(highs) - current) < avg_range * 1.5:
        score += 1.5
        explanation.append("✓ Próximo à resistência")

    volumes = [c["volume"] for c in candles_m1[-20:]]
    avg_vol = sum(volumes[:-1]) / max(len(volumes)-1, 1)
    if volumes[-1] > avg_vol * 1.5:
        score += 0.5
        explanation.append("✓ Volume acima da média")

    if score < 5.5:
        return None

    confidence = round(min(60 + (score / 7.0) * 37, 96), 1)

    return {
        "asset": symbol,
        "direction": "CALL" if direction == 1 else "PUT",
        "timeframe": "M5",
        "confidence": confidence,
        "confluence_score": round(score, 1),
        "entry_price": round(current, 6),
        "expiry": "5 minutos",
        "explanation": explanation,
        "quality": "EXCELENTE" if score >= 6.5 else "BOM",
        "rsi": rsi_m5,
        "pattern": pattern_name,
        "timestamp": datetime.utcnow().strftime("%H:%M UTC"),
    }

def run_scan():
    state["scanning"] = True
    new_signals = []
    for asset in ASSETS:
        symbol = asset["symbol"]
        try:
            candles_m5 = fetch_candles(symbol, "5min", 60)
            time.sleep(0.8)
            candles_m1 = fetch_candles(symbol, "1min", 60)
            time.sleep(0.8)
            signal = analyze_asset(symbol, candles_m5, candles_m1)
            if signal:
                new_signals.append(signal)
                print(f"Sinal: {symbol} {signal['direction']} score={signal['confluence_score']}")
        except Exception as e:
            print(f"Erro {symbol}: {e}")
    new_signals.sort(key=lambda s: s["confluence_score"], reverse=True)
    state["signals"] = new_signals[:5]
    state["last_scan"] = datetime.utcnow().strftime("%H:%M UTC")
    state["scan_count"] += 1
    state["scanning"] = False
    print(f"Scan #{state['scan_count']} — {len(new_signals)} sinais")

def scanner_loop():
    time.sleep(5)
    while True:
        try:
            run_scan()
        except Exception as e:
            print(f"Erro scanner: {e}")
        time.sleep(120)

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>⚡ NEXUS AI Signals</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#030a14;--bg2:#071422;--green:#00e5a0;--red:#ff3d6b;--gold:#f5c842;--blue:#3d9eff;--text:#c8d8e8;--muted:#3a5060;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;}
header{background:rgba(3,10,20,0.97);border-bottom:1px solid rgba(0,200,150,0.12);padding:14px 16px;position:sticky;top:0;z-index:99;display:flex;align-items:center;justify-content:space-between;}
.logo-icon{width:36px;height:36px;background:linear-gradient(135deg,#7b2fff,#00e5a0);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;margin-right:10px;}
.logo{display:flex;align-items:center;}
.logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:16px;}
.logo-text span{color:var(--green);}
.live{display:flex;align-items:center;gap:6px;background:rgba(0,229,160,0.08);border:1px solid rgba(0,229,160,0.2);border-radius:20px;padding:5px 12px;font-size:10px;color:var(--green);letter-spacing:.1em;}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 1.5s infinite;}
.scanbar{background:var(--bg2);border-bottom:1px solid rgba(0,200,150,0.12);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;font-size:11px;}
.progress{height:3px;background:#0a1c30;overflow:hidden;}
.progress-inner{height:100%;width:30%;background:linear-gradient(90deg,transparent,var(--green),transparent);animation:scan 2.5s linear infinite;}
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid rgba(0,200,150,0.12);overflow-x:auto;}
.tab{flex:1;padding:12px 8px;text-align:center;font-size:10px;letter-spacing:.08em;font-family:'Syne',sans-serif;color:var(--muted);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;white-space:nowrap;font-weight:700;}
.tab.active{color:var(--green);border-bottom-color:var(--green);background:rgba(0,229,160,0.04);}
.content{padding:16px;max-width:480px;margin:0 auto;}
.page{display:none;}.page.active{display:block;}
.card{background:var(--bg2);border:1px solid rgba(0,200,150,0.12);border-radius:14px;padding:18px;margin-bottom:14px;position:relative;overflow:hidden;animation:fadeIn .4s ease;}
.card.call{border-color:rgba(0,229,160,0.3);}
.card.put{border-color:rgba(255,61,107,0.3);}
.glow{position:absolute;top:0;left:0;right:0;height:1px;}
.card.call .glow{background:linear-gradient(90deg,transparent,rgba(0,229,160,.7),transparent);}
.card.put .glow{background:linear-gradient(90deg,transparent,rgba(255,61,107,.7),transparent);}
.sig-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px;}
.dir-badge{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:700;letter-spacing:.05em;margin-bottom:6px;}
.call-b{background:rgba(0,229,160,.12);border:1px solid rgba(0,229,160,.35);color:var(--green);}
.put-b{background:rgba(255,61,107,.12);border:1px solid rgba(255,61,107,.35);color:var(--red);}
.asset{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:#e8f0f8;}
.asset-sub{font-size:10px;color:var(--muted);margin-top:2px;}
.conf{font-family:'Syne',sans-serif;font-size:30px;font-weight:800;line-height:1;text-align:right;}
.conf-lbl{font-size:9px;color:var(--muted);letter-spacing:.1em;margin-top:3px;text-align:right;}
.stats3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px;}
.sbox{background:rgba(3,10,20,.7);border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:10px 8px;text-align:center;}
.sval{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:#e8f0f8;}
.slbl{font-size:8px;color:var(--muted);margin-top:3px;letter-spacing:.1em;}
.expl{font-size:11px;color:#7a9ab0;padding:5px 10px;margin-bottom:4px;border-left:2px solid rgba(0,229,160,.2);background:rgba(0,229,160,.02);border-radius:0 6px 6px 0;}
.price-row{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid rgba(255,255,255,.05);margin-bottom:12px;}
.btn-c{width:100%;padding:16px;background:linear-gradient(135deg,#00c882,#00e5a0);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#030a14;cursor:pointer;letter-spacing:.05em;box-shadow:0 4px 20px rgba(0,229,160,.3);margin-bottom:8px;}
.btn-p{width:100%;padding:16px;background:linear-gradient(135deg,#cc1a44,#ff3d6b);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#fff;cursor:pointer;letter-spacing:.05em;box-shadow:0 4px 20px rgba(255,61,107,.3);margin-bottom:8px;}
.outcome-row{display:flex;gap:8px;margin-top:4px;}
.btn-w{flex:1;padding:10px;background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.3);border-radius:8px;color:var(--green);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer;}
.btn-l{flex:1;padding:10px;background:rgba(255,61,107,.1);border:1px solid rgba(255,61,107,.3);border-radius:8px;color:var(--red);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer;}
.empty{text-align:center;padding:60px 20px;color:var(--muted);font-size:13px;}
.empty .icon{font-size:48px;margin-bottom:16px;}
.spin{animation:spin 1.5s linear infinite;display:inline-block;}
.hrow{display:grid;grid-template-columns:1fr 60px 60px 70px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.03);font-size:11px;align-items:center;background:var(--bg2);border-radius:8px;margin-bottom:6px;}
.wb{background:rgba(0,229,160,.1);color:var(--green);border:1px solid rgba(0,229,160,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center;}
.lb{background:rgba(255,61,107,.1);color:var(--red);border:1px solid rgba(255,61,107,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center;}
.pcard{background:var(--bg2);border:1px solid rgba(0,200,150,0.12);border-radius:12px;padding:16px;margin-bottom:12px;}
.ptitle{font-size:9px;color:var(--muted);letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px;}
.bigstat{font-family:'Syne',sans-serif;font-size:42px;font-weight:800;color:var(--green);line-height:1;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes scan{0%{transform:translateX(-200%)}100%{transform:translateX(600%)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">⚡</div>
    <div>
      <div class="logo-text">NEXUS<span>·AI</span></div>
      <div style="font-size:9px;color:var(--muted);letter-spacing:.1em">M1 + M5 SIGNALS</div>
    </div>
  </div>
  <div class="live"><div class="dot"></div>LIVE</div>
</header>
<div class="scanbar">
  <span id="scan-status" style="color:var(--muted)">Iniciando scanner...</span>
  <span id="scan-count" style="color:var(--blue)">0 scans</span>
</div>
<div class="progress"><div class="progress-inner"></div></div>
<div class="tabs">
  <button class="tab active" onclick="showTab('signals',this)">⚡ SINAIS</button>
  <button class="tab" onclick="showTab('history',this)">📋 HISTÓRICO</button>
  <button class="tab" onclick="showTab('performance',this)">📊 STATS</button>
</div>
<div class="content">
  <div id="page-signals" class="page active">
    <div id="signals-container">
      <div class="empty">
        <div class="icon"><span class="spin">⚡</span></div>
        <div style="font-family:'Syne',sans-serif;font-size:16px;color:#e8f0f8;margin-bottom:8px">Escaneando mercados...</div>
        <div>Aguarde o primeiro scan (1-2 min)</div>
      </div>
    </div>
  </div>
  <div id="page-history" class="page">
    <div id="history-container">
      <div class="empty"><div class="icon">📋</div><div>Nenhum trade registrado ainda</div></div>
    </div>
  </div>
  <div id="page-performance" class="page">
    <div class="pcard">
      <div class="ptitle">Win Rate Geral</div>
      <div class="bigstat" id="wr">—</div>
      <div style="font-size:11px;color:var(--muted);margin-top:6px" id="ptotal">0 trades</div>
    </div>
    <div class="stats3">
      <div class="sbox"><div class="sval" id="pw" style="color:var(--green)">0</div><div class="slbl">WINS</div></div>
      <div class="sbox"><div class="sval" id="pl" style="color:var(--red)">0</div><div class="slbl">LOSSES</div></div>
      <div class="sbox"><div class="sval" id="ps" style="color:var(--blue)">0</div><div class="slbl">SCANS</div></div>
    </div>
    <div class="pcard">
      <div class="ptitle">Como registrar</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.7">Após o trade expirar, toque em <span style="color:var(--green)">✓ WIN</span> ou <span style="color:var(--red)">✗ LOSS</span> no card do sinal para registrar o resultado.</div>
    </div>
  </div>
</div>
<script>
let history=JSON.parse(localStorage.getItem('qh')||'[]');
let stats=JSON.parse(localStorage.getItem('qs')||'{"w":0,"l":0}');
function showTab(t,el){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  document.getElementById('page-'+t).classList.add('active');
  el.classList.add('active');
  if(t==='performance')updatePerf();
  if(t==='history')renderHistory();
}
function cc(v){return v>=85?'#00e5a0':v>=75?'#f5c842':'#ff9a3c';}
function renderSignals(data){
  const c=document.getElementById('signals-container');
  document.getElementById('scan-status').textContent=data.scanning?'⚡ Escaneando...':`Último: ${data.last_scan||'—'}`;
  document.getElementById('scan-count').textContent=`${data.scan_count} scans`;
  document.getElementById('ps').textContent=data.scan_count;
  if(!data.signals||data.signals.length===0){
    c.innerHTML=`<div class="empty"><div class="icon">🔍</div><div style="font-family:'Syne',sans-serif;font-size:15px;color:#e8f0f8;margin-bottom:8px">Nenhum sinal agora</div><div>Scanner analisando ${data.total_assets||8} ativos.<br>Aguarde o próximo scan.</div><div style="margin-top:12px;font-size:10px;color:var(--muted)">Último scan: ${data.last_scan||'—'}</div></div>`;
    return;
  }
  let html='';
  data.signals.forEach((s,i)=>{
    const isC=s.direction==='CALL';
    const cf=cc(s.confidence);
    html+=`<div class="card ${isC?'call':'put'}" id="sig-${i}">
    <div class="glow"></div>
    <div class="sig-header">
      <div>
        <div class="${isC?'call-b':'put-b'} dir-badge">${isC?'▲':'▼'} ${s.direction}</div>
        <div class="asset">${s.asset}</div>
        <div class="asset-sub">${s.timeframe} · ${s.expiry}</div>
      </div>
      <div>
        <div class="conf" style="color:${cf}">${s.confidence}%</div>
        <div class="conf-lbl">CONFIANÇA</div>
      </div>
    </div>
    <div class="stats3">
      <div class="sbox"><div class="sval">${s.confluence_score}</div><div class="slbl">SCORE</div></div>
      <div class="sbox"><div class="sval" style="font-size:11px;color:${s.quality==='EXCELENTE'?'#f5c842':'#00e5a0'}">${s.quality}</div><div class="slbl">QUALIDADE</div></div>
      <div class="sbox"><div class="sval" style="font-size:10px">${s.timestamp}</div><div class="slbl">HORA</div></div>
    </div>
    <div style="margin-bottom:14px">${(s.explanation||[]).map(e=>`<div class="expl">${e}</div>`).join('')}</div>
    <div class="price-row"><span style="font-size:10px;color:var(--muted)">Preço entrada</span><span style="font-size:12px;font-weight:700;color:#e8f0f8">${s.entry_price}</span></div>
    <button class="${isC?'btn-c':'btn-p'}">ABRIR ${s.direction} → ${s.asset}</button>
    <div class="outcome-row">
      <button class="btn-w" onclick="rec(${i},'WIN','${s.asset}','${s.direction}',${s.confidence})">✓ WIN</button>
      <button class="btn-l" onclick="rec(${i},'LOSS','${s.asset}','${s.direction}',${s.confidence})">✗ LOSS</button>
    </div></div>`;
  });
  c.innerHTML=html;
}
function rec(i,o,a,d,cf){
  history.unshift({asset:a,direction:d,confidence:cf,outcome:o,time:new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})});
  if(history.length>100)history.pop();
  localStorage.setItem('qh',JSON.stringify(history));
  if(o==='WIN')stats.w++;else stats.l++;
  localStorage.setItem('qs',JSON.stringify(stats));
  fetch('/api/outcome',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({outcome:o})}).catch(()=>{});
  const card=document.getElementById('sig-'+i);
  if(card){card.style.borderColor=o==='WIN'?'#00e5a0':'#ff3d6b';card.style.background=`rgba(${o==='WIN'?'0,229,160':'255,61,107'},.05)`;}
  updatePerf();
  alert(`✅ ${o} registrado para ${a}!`);
}
function renderHistory(){
  const c=document.getElementById('history-container');
  if(!history.length){c.innerHTML='<div class="empty"><div class="icon">📋</div><div>Nenhum trade registrado</div></div>';return;}
  let html=`<div style="display:grid;grid-template-columns:1fr 55px 55px 60px;padding:8px 14px;font-size:9px;color:var(--muted);letter-spacing:.08em;margin-bottom:4px"><span>ATIVO</span><span>DIR.</span><span>HORA</span><span>RES.</span></div>`;
  history.slice(0,50).forEach(h=>{
    html+=`<div class="hrow"><div><div style="color:#e8f0f8;font-weight:700">${h.asset}</div><div style="font-size:9px;color:var(--muted)">${h.confidence}%</div></div><div style="color:${h.direction==='CALL'?'#00e5a0':'#ff3d6b'};font-weight:700;font-size:11px">${h.direction==='CALL'?'▲':'▼'}</div><div style="color:var(--muted);font-size:10px">${h.time}</div><div class="${h.outcome==='WIN'?'wb':'lb'}">${h.outcome}</div></div>`;
  });
  c.innerHTML=html;
}
function updatePerf(){
  const t=stats.w+stats.l;
  const wr=t>0?((stats.w/t)*100).toFixed(1)+'%':'—';
  document.getElementById('wr').textContent=wr;
  document.getElementById('wr').style.color=parseFloat(wr)>=60?'#00e5a0':'#ff3d6b';
  document.getElementById('ptotal').textContent=`${t} trades registrados`;
  document.getElementById('pw').textContent=stats.w;
  document.getElementById('pl').textContent=stats.l;
}
async function fetchSignals(){
  try{
    const r=await fetch('/api/signals');
    const d=await r.json();
    renderSignals(d);
  }catch(e){document.getElementById('scan-status').textContent='⚠ Servidor iniciando...';}
}
fetchSignals();
setInterval(fetchSignals,30000);
updatePerf();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/signals")
def get_signals():
    return jsonify({
        "signals": state["signals"],
        "last_scan": state["last_scan"],
        "scan_count": state["scan_count"],
        "scanning": state["scanning"],
        "total_assets": len(ASSETS),
    })

@app.route("/api/outcome", methods=["POST"])
def record_outcome():
    return jsonify({"status": "ok"})

@app.route("/ping")
def ping():
    return "pong", 200

if __name__ == "__main__":
    t = threading.Thread(target=scanner_loop, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

t = threading.Thread(target=scanner_loop, daemon=True)
t.start()
