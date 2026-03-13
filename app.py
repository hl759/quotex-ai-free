from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import requests
import time
import threading
import os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ─── Chaves API rotativas (até 3 contas gratuitas) ───
# No Render coloque: TWELVE_DATA_KEYS=chave1,chave2,chave3
API_KEYS = [k.strip() for k in os.environ.get("TWELVE_DATA_KEYS", os.environ.get("TWELVE_DATA_KEY", "demo")).split(",") if k.strip()]
key_index = [0]
key_lock  = threading.Lock()

def next_key():
    with key_lock:
        key = API_KEYS[key_index[0] % len(API_KEYS)]
        key_index[0] += 1
        return key

# ─── Ativos ───────────────────────────────────
ASSETS = [
    {"symbol": "EUR/USD", "type": "forex"},
    {"symbol": "GBP/USD", "type": "forex"},
    {"symbol": "USD/JPY", "type": "forex"},
    {"symbol": "AUD/USD", "type": "forex"},
    {"symbol": "USD/CAD", "type": "forex"},
    {"symbol": "USD/CHF", "type": "forex"},
    {"symbol": "NZD/USD", "type": "forex"},
    {"symbol": "EUR/GBP", "type": "forex"},
    {"symbol": "GBP/JPY", "type": "forex"},
    {"symbol": "EUR/JPY", "type": "forex"},
    {"symbol": "EUR/CHF", "type": "forex"},
    {"symbol": "AUD/JPY", "type": "forex"},
    {"symbol": "GBP/CHF", "type": "forex"},
    {"symbol": "CAD/JPY", "type": "forex"},
    {"symbol": "BTC/USD", "type": "crypto"},
    {"symbol": "ETH/USD", "type": "crypto"},
    {"symbol": "LTC/USD", "type": "crypto"},
    {"symbol": "XRP/USD", "type": "crypto"},
    {"symbol": "ADA/USD", "type": "crypto"},
    {"symbol": "SOL/USD", "type": "crypto"},
]

# ─── Aprendizado ──────────────────────────────
DEFAULT_WEIGHTS = {
    "ema_stack": 2.0, "ema_partial": 1.0,
    "rsi_strong": 1.0, "rsi_mild": 0.5,
    "pattern": 1.5, "sr_zone": 1.5, "volume": 0.5,
}
learning = {
    "weights": dict(DEFAULT_WEIGHTS),
    "asset_stats": {}, "hour_stats": {}, "pattern_stats": {},
    "total_trades": 0, "total_wins": 0,
}

def update_weights():
    w = learning["weights"]
    for pat, s in learning["pattern_stats"].items():
        t = s["w"] + s["l"]
        if t >= 10:
            w["pattern"] = round(0.5 + (s["w"]/t) * 2.0, 2)
    for k in w:
        w[k] = max(0.1, min(3.0, w[k]))

def record_learning(data, outcome):
    win = outcome == "WIN"
    a = data.get("asset", "")
    if a not in learning["asset_stats"]:
        learning["asset_stats"][a] = {"w": 0, "l": 0}
    if win: learning["asset_stats"][a]["w"] += 1
    else:   learning["asset_stats"][a]["l"] += 1
    h = str(datetime.now(timezone.utc).hour)
    if h not in learning["hour_stats"]:
        learning["hour_stats"][h] = {"w": 0, "l": 0}
    if win: learning["hour_stats"][h]["w"] += 1
    else:   learning["hour_stats"][h]["l"] += 1
    p = data.get("pattern", "")
    if p:
        if p not in learning["pattern_stats"]:
            learning["pattern_stats"][p] = {"w": 0, "l": 0}
        if win: learning["pattern_stats"][p]["w"] += 1
        else:   learning["pattern_stats"][p]["l"] += 1
    learning["total_trades"] += 1
    if win: learning["total_wins"] += 1
    if learning["total_trades"] % 10 == 0:
        update_weights()

def asset_grade(name):
    s = learning["asset_stats"].get(name)
    if not s: return "NEW", 0
    t = s["w"] + s["l"]
    if t < 5: return "NEW", 0
    wr = s["w"] / t * 100
    if wr >= 70: return "A", round(wr,1)
    if wr >= 60: return "B", round(wr,1)
    if wr >= 50: return "C", round(wr,1)
    return "D", round(wr,1)

def bad_hour():
    h  = datetime.now(timezone.utc).hour
    wd = datetime.now(timezone.utc).weekday()
    if wd >= 5: return True, "Fim de semana — mercado fechado"
    if 0 <= h <= 4: return True, "Madrugada — mercado sem volume"
    hs = learning["hour_stats"].get(str(h))
    if hs:
        t = hs["w"] + hs["l"]
        if t >= 10 and (hs["w"]/t) < 0.40:
            return True, "Histórico ruim nesse horário"
    return False, ""

# ─── Buscar candles Twelve Data ───────────────
def fetch(symbol, interval, outputsize=60):
    try:
        key  = next_key()
        url  = "https://api.twelvedata.com/time_series"
        resp = requests.get(url, params={
            "symbol": symbol, "interval": interval,
            "outputsize": outputsize, "apikey": key,
        }, timeout=10)
        data = resp.json()
        if "values" not in data:
            print(f"Sem dados {symbol} {interval}: {data.get('message','')}")
            return None
        candles = []
        for v in reversed(data["values"]):
            candles.append({
                "open":   float(v["open"]),
                "high":   float(v["high"]),
                "low":    float(v["low"]),
                "close":  float(v["close"]),
                "volume": float(v.get("volume", 1)),
            })
        return candles
    except Exception as e:
        print(f"Erro fetch {symbol}: {e}")
        return None

# ─── Indicadores ─────────────────────────────
def ema(closes, period):
    if len(closes) < period: return float(closes[-1])
    a = 2.0 / (period + 1)
    v = float(closes[0])
    for c in closes[1:]: v = a*float(c)+(1-a)*v
    return v

def rsi(closes, period=14):
    if len(closes) < period+1: return 50.0
    closes = [float(c) for c in closes]
    d  = [closes[i+1]-closes[i] for i in range(len(closes)-1)]
    g  = [x if x>0 else 0 for x in d]
    l  = [-x if x<0 else 0 for x in d]
    ag = sum(g[:period])/period
    al = sum(l[:period])/period
    for i in range(period, len(d)):
        ag = (ag*(period-1)+g[i])/period
        al = (al*(period-1)+l[i])/period
    if al == 0: return 100.0
    return round(100-(100/(1+ag/al)), 2)

def sideways(candles, n=15):
    if len(candles) < n: return False
    hi = [c["high"]  for c in candles[-n:]]
    lo = [c["low"]   for c in candles[-n:]]
    cl = [c["close"] for c in candles[-n:]]
    rng = max(hi)-min(lo)
    avg = sum(cl)/len(cl)
    if avg > 0 and rng/avg < 0.003: return True
    atrs = [hi[i]-lo[i] for i in range(len(hi))]
    avg_a = sum(atrs)/len(atrs)
    if avg_a > 0 and sum(atrs[-3:])/3 < avg_a*0.4: return True
    return False

def pattern(candles):
    if len(candles) < 2: return None, 0
    c  = candles
    body = abs(c[-1]["close"]-c[-1]["open"])
    rng  = c[-1]["high"]-c[-1]["low"]
    if rng == 0: return None, 0
    uw = c[-1]["high"]-max(c[-1]["close"],c[-1]["open"])
    lw = min(c[-1]["close"],c[-1]["open"])-c[-1]["low"]
    if c[-2]["close"]<c[-2]["open"] and c[-1]["close"]>c[-1]["open"] and c[-1]["open"]<c[-2]["close"] and c[-1]["close"]>c[-2]["open"]:
        return "BULLISH ENGULFING", 1
    if c[-2]["close"]>c[-2]["open"] and c[-1]["close"]<c[-1]["open"] and c[-1]["open"]>c[-2]["close"] and c[-1]["close"]<c[-2]["open"]:
        return "BEARISH ENGULFING", -1
    if lw>body*2 and uw<body*0.5 and body>0: return "HAMMER", 1
    if uw>body*2 and lw<body*0.5 and body>0: return "SHOOTING STAR", -1
    if lw>rng*0.6: return "BULLISH PIN BAR", 1
    if uw>rng*0.6: return "BEARISH PIN BAR", -1
    return None, 0

def analyze(name, m5, m1):
    if not m5 or not m1 or len(m5)<30 or len(m1)<30: return None
    if sideways(m5): return None
    c5  = [c["close"] for c in m5]
    c1  = [c["close"] for c in m1]
    cur = c5[-1]
    e9  = ema(c5,9); e21=ema(c5,21); e50=ema(c5,min(50,len(c5)-1))
    e9m = ema(c1,9); e21m=ema(c1,21)
    r5  = rsi(c5)
    t5  = 1 if e9>e21>e50 else (-1 if e9<e21<e50 else 0)
    t1  = 1 if e9m>e21m else (-1 if e9m<e21m else 0)
    if t5==0 or t1==0 or t5!=t1: return None
    if 45<=r5<=55: return None
    if t5==1 and r5>65: return None
    if t5==-1 and r5<35: return None
    pname, pdir = pattern(m1[-5:])
    if not pname or pdir!=t5: return None
    w = learning["weights"]
    score = 0.0; expl = []
    if t5==1 and e9>e21>e50:
        score+=w["ema_stack"]; expl.append("✓ EMA bullish stack (9>21>50)")
    elif t5==-1 and e9<e21<e50:
        score+=w["ema_stack"]; expl.append("✓ EMA bearish stack (9<21<50)")
    else:
        score+=w["ema_partial"]
    if t5==1 and r5<42:
        score+=w["rsi_strong"]; expl.append(f"✓ RSI sobrevendido {r5:.1f}")
    elif t5==-1 and r5>58:
        score+=w["rsi_strong"]; expl.append(f"✓ RSI sobrecomprado {r5:.1f}")
    else:
        score+=w["rsi_mild"]; expl.append(f"✓ RSI favorável {r5:.1f}")
    score+=w["pattern"]; expl.append(f"✓ Padrão: {pname}")
    hi = [c["high"] for c in m5[-20:]]
    lo = [c["low"]  for c in m5[-20:]]
    ar = sum(h-l for h,l in zip(hi,lo))/len(hi)
    if t5==1 and (cur-min(lo))<ar*1.5:
        score+=w["sr_zone"]; expl.append("✓ Próximo ao suporte")
    elif t5==-1 and (max(hi)-cur)<ar*1.5:
        score+=w["sr_zone"]; expl.append("✓ Próximo à resistência")
    vols = [c["volume"] for c in m1[-20:]]
    avgv = sum(vols[:-1])/max(len(vols)-1,1)
    if avgv>0 and vols[-1]>avgv*1.5:
        score+=w["volume"]; expl.append("✓ Volume acima da média")
    if score < 5.5: return None
    grade, awr = asset_grade(name)
    if grade == "D": return None
    conf = round(min(60+(score/7.0)*37, 96), 1)
    if grade=="A": conf=min(conf+3,96); expl.append(f"✓ Nota A ({awr}% win rate)")
    elif grade=="B": conf=min(conf+1,96)
    return {
        "asset": name, "direction": "CALL" if t5==1 else "PUT",
        "timeframe": "M1+M5", "confidence": conf,
        "confluence_score": round(score,1),
        "entry_price": round(cur,6), "expiry": "5 minutos",
        "expiry_seconds": 300, "explanation": expl,
        "quality": "EXCELENTE" if score>=6.5 else "BOM",
        "rsi": r5, "pattern": pname, "asset_grade": grade,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
    }

# ─── Estado ───────────────────────────────────
state = {
    "signals": [], "last_scan": None,
    "scan_count": 0, "scanning": False,
    "blocked_reason": "", "credits_used": 0,
}

def run_scan():
    state["scanning"] = True
    bh, reason = bad_hour()
    if bh:
        state.update({"scanning":False,"blocked_reason":reason,
            "last_scan":datetime.now(timezone.utc).strftime("%H:%M UTC")})
        state["scan_count"] += 1
        print(f"Bloqueado: {reason}")
        return
    state["blocked_reason"] = ""
    signals = []
    credits = 0
    for asset in ASSETS:
        name = asset["symbol"]
        try:
            grade, _ = asset_grade(name)
            if grade == "D":
                print(f"Pulando {name} — nota D")
                continue
            m5 = fetch(name, "5min", 60)
            credits += 1
            time.sleep(0.6)
            m1 = fetch(name, "1min", 60)
            credits += 1
            time.sleep(0.6)
            sig = analyze(name, m5, m1)
            if sig:
                signals.append(sig)
                print(f"✅ SINAL: {name} {sig['direction']} score={sig['confluence_score']}")
        except Exception as e:
            print(f"Erro {name}: {e}")
    signals.sort(key=lambda s: s["confluence_score"], reverse=True)
    state["signals"]      = signals[:5]
    state["last_scan"]    = datetime.now(timezone.utc).strftime("%H:%M UTC")
    state["scan_count"]  += 1
    state["credits_used"] += credits
    state["scanning"]     = False
    print(f"Scan #{state['scan_count']} — {len(signals)} sinais — {credits} créditos usados — total: {state['credits_used']}")

def scanner_loop():
    print("Scanner iniciando em 5 segundos...")
    time.sleep(5)
    while True:
        print(f"Iniciando scan #{state['scan_count']+1}...")
        try:
            run_scan()
        except Exception as e:
            print(f"Erro: {e}")
            state["scanning"] = False
        # Intervalo inteligente baseado no número de chaves
        interval = max(120, 800 // max(len(API_KEYS), 1))
        print(f"Próximo scan em {interval}s ({len(API_KEYS)} chave(s) ativas)")
        time.sleep(interval)

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>⚡ NEXUS AI</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#030a14;--bg2:#071422;--bg3:#0a1c30;--green:#00e5a0;--red:#ff3d6b;--gold:#f5c842;--blue:#3d9eff;--purple:#7b2fff;--text:#c8d8e8;--muted:#3a5060;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;}
header{background:rgba(3,10,20,.97);border-bottom:1px solid rgba(123,47,255,.2);padding:14px 16px;position:sticky;top:0;z-index:99;display:flex;align-items:center;justify-content:space-between;}
.logo{display:flex;align-items:center;}
.logo-icon{width:38px;height:38px;background:linear-gradient(135deg,#7b2fff,#00e5a0);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-right:10px;}
.logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:17px;}
.logo-text span{color:var(--green);}
.live{display:flex;align-items:center;gap:6px;background:rgba(0,229,160,.08);border:1px solid rgba(0,229,160,.2);border-radius:20px;padding:5px 12px;font-size:10px;color:var(--green);letter-spacing:.1em;}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 1.5s infinite;}
.scanbar{background:var(--bg2);border-bottom:1px solid rgba(123,47,255,.15);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;font-size:11px;}
.progress{height:3px;background:var(--bg3);overflow:hidden;}
.prog-inner{height:100%;width:30%;background:linear-gradient(90deg,transparent,var(--purple),var(--green),transparent);animation:scan 2.5s linear infinite;}
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid rgba(123,47,255,.15);overflow-x:auto;}
.tab{flex:1;padding:12px 6px;text-align:center;font-size:10px;letter-spacing:.06em;font-family:'Syne',sans-serif;color:var(--muted);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;white-space:nowrap;font-weight:700;}
.tab.active{color:var(--green);border-bottom-color:var(--green);background:rgba(0,229,160,.04);}
.content{padding:16px;max-width:480px;margin:0 auto;}
.page{display:none;}.page.active{display:block;}
.card{background:var(--bg2);border:1px solid rgba(123,47,255,.2);border-radius:14px;padding:18px;margin-bottom:14px;position:relative;overflow:hidden;animation:fadeIn .4s ease;}
.card.call{border-color:rgba(0,229,160,.3);}
.card.put{border-color:rgba(255,61,107,.3);}
.glow{position:absolute;top:0;left:0;right:0;height:1px;}
.card.call .glow{background:linear-gradient(90deg,transparent,rgba(0,229,160,.8),transparent);}
.card.put .glow{background:linear-gradient(90deg,transparent,rgba(255,61,107,.8),transparent);}
.sig-hdr{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px;}
.dbadge{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:700;margin-bottom:6px;}
.cb{background:rgba(0,229,160,.12);border:1px solid rgba(0,229,160,.35);color:var(--green);}
.pb{background:rgba(255,61,107,.12);border:1px solid rgba(255,61,107,.35);color:var(--red);}
.aname{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:#e8f0f8;}
.asub{font-size:10px;color:var(--muted);margin-top:2px;}
.conf{font-family:'Syne',sans-serif;font-size:30px;font-weight:800;line-height:1;text-align:right;}
.clbl{font-size:9px;color:var(--muted);letter-spacing:.1em;margin-top:3px;text-align:right;}
.s3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px;}
.sbox{background:rgba(3,10,20,.7);border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:10px 8px;text-align:center;}
.sv{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:#e8f0f8;}
.sl{font-size:8px;color:var(--muted);margin-top:3px;letter-spacing:.1em;}
.expl{font-size:11px;color:#7a9ab0;padding:5px 10px;margin-bottom:4px;border-left:2px solid rgba(0,229,160,.2);background:rgba(0,229,160,.02);border-radius:0 6px 6px 0;}
.prow{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid rgba(255,255,255,.05);margin-bottom:10px;}
.tbar{background:rgba(3,10,20,.7);border:1px solid rgba(255,255,255,.05);border-radius:8px;padding:8px 12px;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;}
.tval{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:var(--gold);}
.ttrack{flex:1;height:4px;background:var(--bg);border-radius:2px;overflow:hidden;margin:0 10px;}
.tfill{height:100%;background:linear-gradient(90deg,var(--red),var(--gold),var(--green));border-radius:2px;transition:width 1s linear;}
.btnc{width:100%;padding:15px;background:linear-gradient(135deg,#00c882,#00e5a0);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#030a14;cursor:pointer;box-shadow:0 4px 20px rgba(0,229,160,.3);margin-bottom:8px;}
.btnp{width:100%;padding:15px;background:linear-gradient(135deg,#cc1a44,#ff3d6b);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#fff;cursor:pointer;box-shadow:0 4px 20px rgba(255,61,107,.3);margin-bottom:8px;}
.orrow{display:flex;gap:8px;margin-top:4px;}
.bw{flex:1;padding:10px;background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.3);border-radius:8px;color:var(--green);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer;}
.bl{flex:1;padding:10px;background:rgba(255,61,107,.1);border:1px solid rgba(255,61,107,.3);border-radius:8px;color:var(--red);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer;}
.empty{text-align:center;padding:50px 20px;color:var(--muted);font-size:13px;}
.empty .icon{font-size:48px;margin-bottom:16px;}
.spin{animation:spin 1.5s linear infinite;display:inline-block;}
.hrow{display:grid;grid-template-columns:1fr 55px 55px 60px;padding:12px 14px;font-size:11px;align-items:center;background:var(--bg2);border-radius:8px;margin-bottom:6px;}
.wb{background:rgba(0,229,160,.1);color:var(--green);border:1px solid rgba(0,229,160,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center;}
.lb{background:rgba(255,61,107,.1);color:var(--red);border:1px solid rgba(255,61,107,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center;}
.pcard{background:var(--bg2);border:1px solid rgba(123,47,255,.2);border-radius:12px;padding:16px;margin-bottom:12px;}
.ptitle{font-size:9px;color:var(--muted);letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px;}
.bigstat{font-family:'Syne',sans-serif;font-size:42px;font-weight:800;line-height:1;}
.hgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin-top:10px;}
.hbox{background:var(--bg3);border-radius:6px;padding:6px 2px;text-align:center;}
.hbox.good{background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.2);}
.hbox.bad{background:rgba(255,61,107,.08);border:1px solid rgba(255,61,107,.15);}
.blocked{background:rgba(255,61,107,.06);border:1px solid rgba(255,61,107,.25);border-radius:10px;padding:12px 16px;margin-bottom:14px;font-size:11px;color:#ff6b8a;text-align:center;}
.alert{background:rgba(245,200,66,.06);border:1px solid rgba(245,200,66,.25);border-radius:10px;padding:12px 16px;margin-bottom:14px;font-size:11px;color:#c8a020;}
.credits-bar{background:rgba(123,47,255,.06);border:1px solid rgba(123,47,255,.2);border-radius:8px;padding:8px 14px;margin-bottom:12px;font-size:10px;color:#9b6fff;display:flex;justify-content:space-between;align-items:center;}
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
      <div style="font-size:9px;color:var(--muted);letter-spacing:.1em">M1 + M5 · 20 ATIVOS · DADOS REAIS</div>
    </div>
  </div>
  <div class="live"><div class="dot"></div>LIVE</div>
</header>
<div class="scanbar">
  <span id="scan-status" style="color:var(--muted)">Iniciando scanner...</span>
  <span id="scan-count" style="color:var(--purple)">0 scans</span>
</div>
<div class="progress"><div class="prog-inner"></div></div>
<div class="tabs">
  <button class="tab active" onclick="showTab('signals',this)">⚡ SINAIS</button>
  <button class="tab" onclick="showTab('history',this)">📋 HISTÓRICO</button>
  <button class="tab" onclick="showTab('perf',this)">📊 STATS</button>
  <button class="tab" onclick="showTab('assets',this)">🏆 ATIVOS</button>
</div>
<div class="content">
  <div id="page-signals" class="page active">
    <div id="sc">
      <div class="empty"><div class="icon"><span class="spin">⚡</span></div>
      <div style="font-family:'Syne',sans-serif;font-size:16px;color:#e8f0f8;margin-bottom:8px">Iniciando NEXUS AI...</div>
      <div>Escaneando 20 ativos com dados reais</div></div>
    </div>
  </div>
  <div id="page-history" class="page"><div id="hc"><div class="empty"><div class="icon">📋</div><div>Nenhum trade registrado</div></div></div></div>
  <div id="page-perf" class="page">
    <div class="pcard"><div class="ptitle">Win Rate Geral</div><div class="bigstat" id="wr" style="color:var(--green)">—</div><div style="font-size:11px;color:var(--muted);margin-top:6px" id="ptotal">0 trades</div></div>
    <div class="s3">
      <div class="sbox"><div class="sv" id="pw" style="color:var(--green)">0</div><div class="sl">WINS</div></div>
      <div class="sbox"><div class="sv" id="pl" style="color:var(--red)">0</div><div class="sl">LOSSES</div></div>
      <div class="sbox"><div class="sv" id="ps" style="color:var(--purple)">0</div><div class="sl">SCANS</div></div>
    </div>
    <div class="pcard"><div class="ptitle">Créditos API</div><div id="credits-info" style="font-size:11px;color:var(--muted);line-height:1.8">Carregando...</div></div>
    <div class="pcard"><div class="ptitle">Win Rate por Horário (UTC)</div><div class="hgrid" id="hgrid"></div></div>
  </div>
  <div id="page-assets" class="page"><div class="pcard"><div class="ptitle">Ranking de Ativos</div><div id="ar"><div style="font-size:11px;color:var(--muted)">Registre trades para ver o ranking.</div></div></div></div>
</div>
<script>
let history=JSON.parse(localStorage.getItem('nx_h')||'[]');
let stats=JSON.parse(localStorage.getItem('nx_s')||'{"w":0,"l":0}');
let hourStats=JSON.parse(localStorage.getItem('nx_hs')||'{}');
let assetStats=JSON.parse(localStorage.getItem('nx_as')||'{}');
let prevSigs=[];let timers={};

function showTab(t,el){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  document.getElementById('page-'+t).classList.add('active');el.classList.add('active');
  if(t==='perf'){updatePerf();renderHGrid();}
  if(t==='history')renderHistory();
  if(t==='assets')renderAssets();
}
function cc(v){return v>=85?'#00e5a0':v>=75?'#f5c842':'#ff9a3c';}
function beep(){
  try{const ctx=new(window.AudioContext||window.webkitAudioContext)();
  const o=ctx.createOscillator(),g=ctx.createGain();
  o.connect(g);g.connect(ctx.destination);
  o.frequency.setValueAtTime(880,ctx.currentTime);o.frequency.setValueAtTime(1100,ctx.currentTime+0.1);o.frequency.setValueAtTime(880,ctx.currentTime+0.2);
  g.gain.setValueAtTime(0.3,ctx.currentTime);g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+0.5);
  o.start();o.stop(ctx.currentTime+0.5);}catch(e){}
}
function startTimer(i,secs,iso){
  if(timers[i])clearInterval(timers[i]);
  const end=(iso?new Date(iso).getTime():Date.now())+secs*1000;
  timers[i]=setInterval(()=>{
    const rem=Math.max(0,Math.floor((end-Date.now())/1000));
    const f=document.getElementById('tf-'+i),v=document.getElementById('tv-'+i);
    if(!f||!v){clearInterval(timers[i]);return;}
    f.style.width=(rem/secs*100)+'%';
    v.textContent=`${Math.floor(rem/60)}:${(rem%60).toString().padStart(2,'0')}`;
    if(rem===0){clearInterval(timers[i]);v.textContent='EXPIROU';v.style.color='#ff3d6b';}
  },1000);
}
function renderSignals(data){
  const c=document.getElementById('sc');
  const used=data.credits_used||0;
  const limit=800*Math.max(data.api_keys||1,1);
  document.getElementById('scan-status').textContent=data.scanning?'⚡ Escaneando...':data.blocked_reason?`🔴 ${data.blocked_reason}`:`Último: ${data.last_scan||'—'}`;
  document.getElementById('scan-count').textContent=`${data.scan_count} scans`;
  document.getElementById('ps').textContent=data.scan_count;
  const ci=document.getElementById('credits-info');
  if(ci)ci.innerHTML=`Créditos usados: <strong style="color:#e8f0f8">${used}</strong> / ${limit}<br>Chaves ativas: <strong style="color:#9b6fff">${data.api_keys||1}</strong><br>Dados: <strong style="color:#00e5a0">Twelve Data — Tempo Real</strong>`;
  if(data.blocked_reason){
    c.innerHTML=`<div class="blocked">🔴 ${data.blocked_reason}</div><div class="empty"><div class="icon">🕐</div><div style="font-family:'Syne',sans-serif;font-size:14px;color:#e8f0f8;margin-bottom:8px">Melhor horário: 06h–17h UTC</div><div style="font-size:11px">(09h–20h horário de Brasília)</div></div>`;
    return;
  }
  if(!data.signals||!data.signals.length){
    c.innerHTML=`<div class="empty"><div class="icon">🔍</div><div style="font-family:'Syne',sans-serif;font-size:15px;color:#e8f0f8;margin-bottom:8px">Nenhum sinal agora</div><div>Analisando 20 ativos M1+M5.<br>Aguarde o próximo scan.</div><div style="margin-top:12px;font-size:10px;color:var(--muted)">Último: ${data.last_scan||'—'}</div></div>`;
    return;
  }
  const newKey=data.signals.map(s=>s.asset+s.direction).join(',');
  const oldKey=prevSigs.map(s=>s.asset+s.direction).join(',');
  if(newKey!==oldKey&&prevSigs.length>0)beep();
  prevSigs=data.signals;
  const hasEx=data.signals.some(s=>s.quality==='EXCELENTE');
  let html=hasEx?`<div class="alert">⭐ Sinal EXCELENTE detectado!</div>`:'';
  data.signals.forEach((s,i)=>{
    const isC=s.direction==='CALL';
    const gc=s.asset_grade==='A'?'#00e5a0':s.asset_grade==='B'?'#3d9eff':s.asset_grade==='C'?'#f5c842':'#888';
    html+=`<div class="card ${isC?'call':'put'}" id="sig-${i}"><div class="glow"></div>
    <div class="sig-hdr"><div><div class="${isC?'cb':'pb'} dbadge">${isC?'▲':'▼'} ${s.direction}</div><div class="aname">${s.asset}</div><div class="asub">${s.timeframe} · ${s.expiry} · <span style="color:${gc}">Nota ${s.asset_grade}</span></div></div>
    <div><div class="conf" style="color:${cc(s.confidence)}">${s.confidence}%</div><div class="clbl">CONFIANÇA</div></div></div>
    <div class="tbar"><span style="font-size:9px;color:var(--muted)">EXPIRA EM</span><div class="ttrack"><div class="tfill" id="tf-${i}" style="width:100%"></div></div><div class="tval" id="tv-${i}">5:00</div></div>
    <div class="s3"><div class="sbox"><div class="sv">${s.confluence_score}</div><div class="sl">SCORE</div></div><div class="sbox"><div class="sv" style="font-size:11px;color:${s.quality==='EXCELENTE'?'#f5c842':'#00e5a0'}">${s.quality}</div><div class="sl">QUALIDADE</div></div><div class="sbox"><div class="sv" style="font-size:10px">${s.timestamp}</div><div class="sl">HORA</div></div></div>
    <div style="margin-bottom:14px">${(s.explanation||[]).map(e=>`<div class="expl">${e}</div>`).join('')}</div>
    <div class="prow"><span style="font-size:10px;color:var(--muted)">Preço entrada</span><span style="font-size:12px;font-weight:700;color:#e8f0f8">${s.entry_price}</span></div>
    <button class="${isC?'btnc':'btnp'}">ABRIR ${s.direction} → ${s.asset}</button>
    <div class="orrow"><button class="bw" onclick="rec(${i},'WIN','${s.asset}','${s.direction}',${s.confidence},'${s.pattern||''}')">✓ WIN</button><button class="bl" onclick="rec(${i},'LOSS','${s.asset}','${s.direction}',${s.confidence},'${s.pattern||''}')">✗ LOSS</button></div></div>`;
  });
  c.innerHTML=html;
  data.signals.forEach((s,i)=>startTimer(i,s.expiry_seconds||300,s.timestamp_iso));
}
function rec(i,o,a,d,cf,pat){
  const w=o==='WIN';
  history.unshift({asset:a,direction:d,confidence:cf,outcome:o,pattern:pat,time:new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})});
  if(history.length>200)history.pop();
  localStorage.setItem('nx_h',JSON.stringify(history));
  if(w)stats.w++;else stats.l++;
  localStorage.setItem('nx_s',JSON.stringify(stats));
  const h=new Date().getUTCHours().toString();
  if(!hourStats[h])hourStats[h]={w:0,l:0};
  if(w)hourStats[h].w++;else hourStats[h].l++;
  localStorage.setItem('nx_hs',JSON.stringify(hourStats));
  if(!assetStats[a])assetStats[a]={w:0,l:0};
  if(w)assetStats[a].w++;else assetStats[a].l++;
  localStorage.setItem('nx_as',JSON.stringify(assetStats));
  fetch('/api/outcome',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({outcome:o,asset:a,pattern:pat,confidence:cf})}).catch(()=>{});
  const card=document.getElementById('sig-'+i);
  if(card){card.style.borderColor=w?'#00e5a0':'#ff3d6b';card.style.background=`rgba(${w?'0,229,160':'255,61,107'},.05)`;}
  updatePerf();alert(`${w?'✅':'❌'} ${o} — ${a}!`);
}
function renderHistory(){
  const c=document.getElementById('hc');
  if(!history.length){c.innerHTML='<div class="empty"><div class="icon">📋</div><div>Nenhum trade</div></div>';return;}
  let html=`<div style="display:grid;grid-template-columns:1fr 55px 55px 60px;padding:8px 14px;font-size:9px;color:var(--muted);letter-spacing:.08em;margin-bottom:4px"><span>ATIVO</span><span>DIR.</span><span>HORA</span><span>RES.</span></div>`;
  history.slice(0,50).forEach(h=>{
    html+=`<div class="hrow"><div><div style="color:#e8f0f8;font-weight:700">${h.asset}</div><div style="font-size:9px;color:var(--muted)">${h.confidence}%</div></div><div style="color:${h.direction==='CALL'?'#00e5a0':'#ff3d6b'};font-weight:700">${h.direction==='CALL'?'▲':'▼'}</div><div style="color:var(--muted);font-size:10px">${h.time}</div><div class="${h.outcome==='WIN'?'wb':'lb'}">${h.outcome}</div></div>`;
  });c.innerHTML=html;
}
function updatePerf(){
  const t=stats.w+stats.l;
  const wr=t>0?((stats.w/t)*100).toFixed(1)+'%':'—';
  const el=document.getElementById('wr');
  el.textContent=wr;el.style.color=parseFloat(wr)>=60?'#00e5a0':'#ff3d6b';
  document.getElementById('ptotal').textContent=`${t} trades`;
  document.getElementById('pw').textContent=stats.w;
  document.getElementById('pl').textContent=stats.l;
}
function renderHGrid(){
  const g=document.getElementById('hgrid');if(!g)return;
  let html='';
  for(let h=0;h<24;h++){
    const hs=hourStats[h.toString()];const t=hs?hs.w+hs.l:0;
    const wr=t>=3?Math.round(hs.w/t*100):null;
    const cls=wr===null?'':wr>=60?'good':wr<45?'bad':'';
    const col=wr===null?'var(--muted)':wr>=60?'var(--green)':wr<45?'var(--red)':'var(--gold)';
    html+=`<div class="hbox ${cls}"><div style="font-size:9px;color:${col}">${h}h</div>${wr!==null?`<div style="font-size:10px;font-weight:700;color:${col}">${wr}%</div>`:''}</div>`;
  }g.innerHTML=html;
}
function renderAssets(){
  const c=document.getElementById('ar');if(!c)return;
  const list=Object.entries(assetStats).map(([s,v])=>{const t=v.w+v.l;const wr=t>0?Math.round(v.w/t*100):0;const g=wr>=70?'A':wr>=60?'B':wr>=50?'C':'D';return{s,t,wr,g};}).filter(a=>a.t>=2).sort((a,b)=>b.wr-a.wr);
  if(!list.length){c.innerHTML='<div style="font-size:11px;color:var(--muted)">Registre pelo menos 2 trades.</div>';return;}
  let html='';
  list.forEach((a,i)=>{
    const col=a.g==='A'?'#00e5a0':a.g==='B'?'#3d9eff':a.g==='C'?'#f5c842':'#ff3d6b';
    html+=`<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)"><div><span style="font-size:12px;color:#e8f0f8;font-weight:700">${i+1}. ${a.s}</span><span style="font-size:10px;color:var(--muted);margin-left:8px">${a.t} trades</span></div><div><span style="font-size:16px;font-weight:800;color:${col}">${a.wr}%</span><span style="font-size:11px;color:${col};margin-left:6px;font-weight:700">Nota ${a.g}</span></div></div>`;
  });c.innerHTML=html;
}
async function fetchSignals(){
  try{
    const r=await fetch('/api/signals');const d=await r.json();
    renderSignals(d);
  }catch(e){document.getElementById('scan-status').textContent='⚠ Servidor iniciando...';}
}
fetchSignals();setInterval(fetchSignals,30000);updatePerf();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/signals")
def api_signals():
    return jsonify({
        "signals": state["signals"], "last_scan": state["last_scan"],
        "scan_count": state["scan_count"], "scanning": state["scanning"],
        "total_assets": len(ASSETS), "blocked_reason": state["blocked_reason"],
        "credits_used": state["credits_used"], "api_keys": len(API_KEYS),
    })

@app.route("/api/outcome", methods=["POST"])
def api_outcome():
    data = request.json or {}
    if data.get("outcome") in ["WIN","LOSS"]:
        record_learning(data, data["outcome"])
    return jsonify({"status":"ok"})

@app.route("/ping")
def ping():
    return "pong", 200

t = threading.Thread(target=scanner_loop, daemon=True)
t.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
