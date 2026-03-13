from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import yfinance as yf
import time
import threading
import os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ─── Ativos ───────────────────────────────────
ASSETS = [
    {"symbol": "EURUSD=X",  "name": "EUR/USD", "type": "forex"},
    {"symbol": "GBPUSD=X",  "name": "GBP/USD", "type": "forex"},
    {"symbol": "USDJPY=X",  "name": "USD/JPY", "type": "forex"},
    {"symbol": "AUDUSD=X",  "name": "AUD/USD", "type": "forex"},
    {"symbol": "USDCAD=X",  "name": "USD/CAD", "type": "forex"},
    {"symbol": "USDCHF=X",  "name": "USD/CHF", "type": "forex"},
    {"symbol": "NZDUSD=X",  "name": "NZD/USD", "type": "forex"},
    {"symbol": "EURGBP=X",  "name": "EUR/GBP", "type": "forex"},
    {"symbol": "GBPJPY=X",  "name": "GBP/JPY", "type": "forex"},
    {"symbol": "EURJPY=X",  "name": "EUR/JPY", "type": "forex"},
    {"symbol": "EURCHF=X",  "name": "EUR/CHF", "type": "forex"},
    {"symbol": "AUDJPY=X",  "name": "AUD/JPY", "type": "forex"},
    {"symbol": "GBPCHF=X",  "name": "GBP/CHF", "type": "forex"},
    {"symbol": "CADJPY=X",  "name": "CAD/JPY", "type": "forex"},
    {"symbol": "BTC-USD",   "name": "BTC/USD", "type": "crypto"},
    {"symbol": "ETH-USD",   "name": "ETH/USD", "type": "crypto"},
    {"symbol": "LTC-USD",   "name": "LTC/USD", "type": "crypto"},
    {"symbol": "XRP-USD",   "name": "XRP/USD", "type": "crypto"},
    {"symbol": "ADA-USD",   "name": "ADA/USD", "type": "crypto"},
    {"symbol": "SOL-USD",   "name": "SOL/USD", "type": "crypto"},
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
    h = datetime.now(timezone.utc).hour
    wd = datetime.now(timezone.utc).weekday()
    if wd >= 5: return True, "Fim de semana — mercado fechado"
    if 0 <= h <= 4: return True, "Madrugada — mercado sem volume"
    hs = learning["hour_stats"].get(str(h))
    if hs:
        t = hs["w"] + hs["l"]
        if t >= 10 and (hs["w"]/t) < 0.40:
            return True, f"Histórico ruim nesse horário"
    return False, ""

# ─── Buscar candles yfinance ──────────────────
def fetch(symbol, interval, period):
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        if df is None or len(df) < 15:
            return None
        candles = []
        for _, row in df.iterrows():
            candles.append({
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]) if row["Volume"] > 0 else 1.0,
            })
        return candles
    except:
        return None

# ─── Indicadores ─────────────────────────────
def ema(closes, period):
    if len(closes) < period: return float(closes[-1])
    a = 2.0 / (period + 1)
    v = float(closes[0])
    for c in closes[1:]: v = a*float(c) + (1-a)*v
    return v

def rsi(closes, period=14):
    if len(closes) < period+1: return 50.0
    closes = [float(c) for c in closes]
    d = [closes[i+1]-closes[i] for i in range(len(closes)-1)]
    g = [x if x>0 else 0 for x in d]
    l = [-x if x<0 else 0 for x in d]
    ag = sum(g[:period])/period
    al = sum(l[:period])/period
    for i in range(period, len(d)):
        ag = (ag*(period-1)+g[i])/period
        al = (al*(period-1)+l[i])/period
    if al == 0: return 100.0
    return round(100-(100/(1+ag/al)), 2)

def sideways(candles, n=15):
    if len(candles) < n: return False
    hi = [c["high"] for c in candles[-n:]]
    lo = [c["low"]  for c in candles[-n:]]
    cl = [c["close"] for c in candles[-n:]]
    rng = max(hi)-min(lo)
    avg = sum(cl)/len(cl)
    if avg > 0 and rng/avg < 0.003: return True
    atrs = [hi[i]-lo[i] for i in range(len(hi))]
    if sum(atrs)/len(atrs) > 0 and sum(atrs[-3:])/3 < sum(atrs)/len(atrs)*0.4:
        return True
    return False

def pattern(candles):
    if len(candles) < 2: return None, 0
    c = candles
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

# ─── Análise ─────────────────────────────────
def analyze(name, m5, m1):
    if not m5 or not m1 or len(m5)<30 or len(m1)<30: return None
    if sideways(m5): return None

    c5 = [c["close"] for c in m5]
    c1 = [c["close"] for c in m1]
    cur = c5[-1]

    e9  = ema(c5,9); e21 = ema(c5,21); e50 = ema(c5,min(50,len(c5)-1))
    e9m = ema(c1,9); e21m= ema(c1,21)
    r5  = rsi(c5)

    t5 = 1 if e9>e21>e50 else (-1 if e9<e21<e50 else 0)
    t1 = 1 if e9m>e21m else (-1 if e9m<e21m else 0)

    if t5==0 or t1==0 or t5!=t1: return None
    if 45<=r5<=55: return None
    if t5==1 and r5>65: return None
    if t5==-1 and r5<35: return None

    pname, pdir = pattern(m1[-5:])
    if not pname or pdir!=t5: return None

    w = learning["weights"]
    score = 0.0
    expl  = []

    if t5==1 and e9>e21>e50:
        score += w["ema_stack"]; expl.append("✓ EMA bullish stack (9>21>50)")
    elif t5==-1 and e9<e21<e50:
        score += w["ema_stack"]; expl.append("✓ EMA bearish stack (9<21<50)")
    else:
        score += w["ema_partial"]

    if t5==1 and r5<42:
        score += w["rsi_strong"]; expl.append(f"✓ RSI sobrevendido {r5:.1f}")
    elif t5==-1 and r5>58:
        score += w["rsi_strong"]; expl.append(f"✓ RSI sobrecomprado {r5:.1f}")
    else:
        score += w["rsi_mild"]; expl.append(f"✓ RSI favorável {r5:.1f}")

    score += w["pattern"]; expl.append(f"✓ Padrão: {pname}")

    hi  = [c["high"] for c in m5[-20:]]
    lo  = [c["low"]  for c in m5[-20:]]
    ar  = sum(h-l for h,l in zip(hi,lo))/len(hi)

    if t5==1 and (cur-min(lo))<ar*1.5:
        score += w["sr_zone"]; expl.append("✓ Próximo ao suporte")
    elif t5==-1 and (max(hi)-cur)<ar*1.5:
        score += w["sr_zone"]; expl.append("✓ Próximo à resistência")

    vols = [c["volume"] for c in m1[-20:]]
    avgv = sum(vols[:-1])/max(len(vols)-1,1)
    if avgv>0 and vols[-1]>avgv*1.5:
        score += w["volume"]; expl.append("✓ Volume acima da média")

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
    "scan_count": 0, "scanning": False, "blocked_reason": "",
}

def run_scan():
    state["scanning"] = True
    bh, reason = bad_hour()
    if bh:
        state.update({"scanning":False,"blocked_reason":reason,
            "last_scan":datetime.now(timezone.utc).strftime("%H:%M UTC")})
        state["scan_count"] += 1
        return

    state["blocked_reason"] = ""
    signals = []

    for asset in ASSETS:
        sym  = asset["symbol"]
        name = asset["name"]
        try:
            grade, _ = asset_grade(name)
            if grade == "D": continue

            m5 = fetch(sym, "5m", "5d")
            time.sleep(0.5)
            m1 = fetch(sym, "1m", "1d")
            time.sleep(0.5)

            sig = analyze(name, m5, m1)
            if sig:
                signals.append(sig)
                print(f"✅ {name} {sig['direction']} {sig['confluence_score']}")
        except Exception as e:
            print(f"Erro {name}: {e}")

    signals.sort(key=lambda s: s["confluence_score"], reverse=True)
    state["signals"]    = signals[:5]
    state["last_scan"]  = datetime.now(timezone.utc).strftime("%H:%M UTC")
    state["scan_count"] += 1
    state["scanning"]   = False
    print(f"Scan #{state['scan_count']} — {len(signals)} sinais")

def scanner_loop():
    time.sleep(8)
    while True:
        try: run_scan()
        except Exception as e: print(f"Erro: {e}")
        time.sleep(120)  # 2 minutos — seguro para yfinance

# ─── HTML ─────────────────────────────────────
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
.btnc{width:100%;padding:15px;background:linear-gradient(135deg,#00c882,#00e5a0);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#030a14;cursor:pointer;letter-spacing:.05em;box-shadow:0 4px 20px rgba(0,229,160,.3);margin-bottom:8px;}
.btnp{width:100%;padding:15px;background:linear-gradient(135deg,#cc1a44,#ff3d6b);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#fff;cursor:pointer;letter-spacing:.05em;box-shadow:0 4px 20px rgba(255,61,107,.3);margin-bottom:8px;}
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
.src{background:rgba(123,47,255,.06);border:1px solid rgba(123,47,255,.2);border-radius:8px;padding:8px 12px;margin-bottom:14px;font-size:10px;color:#9b6fff;text-align:center;}
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
      <div style="font-size:9px;color:var(--muted);letter-spacing:.1em">M1 + M5 · 20 ATIVOS · SEM LIMITE</div>
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
  <button class="tab" o
