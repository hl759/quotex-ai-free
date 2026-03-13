from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import requests, time, threading, os
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")

ASSETS = [
    {"symbol": "EUR/USD"}, {"symbol": "GBP/USD"}, {"symbol": "USD/JPY"},
    {"symbol": "GBP/JPY"}, {"symbol": "EUR/JPY"}, {"symbol": "BTC/USD"},
    {"symbol": "ETH/USD"}, {"symbol": "XRP/USD"}, {"symbol": "ADA/USD"},
    {"symbol": "SOL/USD"},
]

SCAN_INTERVAL = 20 * 60
MAX_CREDITS   = 780
REQ_DELAY     = 4.0

credits_today = {"count": 0, "day": datetime.now(timezone.utc).day}

def check_reset():
    today = datetime.now(timezone.utc).day
    if credits_today["day"] != today:
        credits_today["count"] = 0
        credits_today["day"]   = today
        print("Creditos resetados!")

DEFAULT_WEIGHTS = {"ema_stack":2.0,"ema_partial":1.0,"rsi_strong":1.0,"rsi_mild":0.5,"pattern":1.5,"sr_zone":1.5,"volume":0.5}
learning = {"weights": dict(DEFAULT_WEIGHTS), "asset_stats":{}, "hour_stats":{}, "pattern_stats":{}, "total_trades":0, "total_wins":0}

def record_learning(data, outcome):
    win = outcome == "WIN"
    a = data.get("asset","")
    if a not in learning["asset_stats"]: learning["asset_stats"][a] = {"w":0,"l":0}
    if win: learning["asset_stats"][a]["w"] += 1
    else:   learning["asset_stats"][a]["l"] += 1
    h = str(datetime.now(timezone.utc).hour)
    if h not in learning["hour_stats"]: learning["hour_stats"][h] = {"w":0,"l":0}
    if win: learning["hour_stats"][h]["w"] += 1
    else:   learning["hour_stats"][h]["l"] += 1
    p = data.get("pattern","")
    if p:
        if p not in learning["pattern_stats"]: learning["pattern_stats"][p] = {"w":0,"l":0}
        if win: learning["pattern_stats"][p]["w"] += 1
        else:   learning["pattern_stats"][p]["l"] += 1
    learning["total_trades"] += 1
    if win: learning["total_wins"] += 1

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
    if wd >= 5: return True, "Fim de semana - mercado fechado"
    if 0 <= h <= 3: return True, "Madrugada - mercado sem volume"
    return False, ""

def fetch(symbol, interval):
    try:
        r = requests.get("https://api.twelvedata.com/time_series", params={
            "symbol": symbol, "interval": interval,
            "outputsize": 80, "apikey": API_KEY,
        }, timeout=12)
        data = r.json()
        credits_today["count"] += 1
        if "values" not in data:
            print(f"  Sem dados {symbol}/{interval}: {data.get('message','')}")
            return None
        candles = []
        for v in reversed(data["values"]):
            candles.append({
                "open":   float(v["open"]),
                "high":   float(v["high"]),
                "low":    float(v["low"]),
                "close":  float(v["close"]),
                "volume": float(v.get("volume") or 1),
            })
        return candles
    except Exception as e:
        print(f"  Erro fetch {symbol}: {e}")
        return None

def ema(closes, period):
    if len(closes) < period: return float(closes[-1])
    a = 2.0 / (period + 1)
    v = float(closes[0])
    for c in closes[1:]: v = a*float(c) + (1-a)*v
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
    return 100.0 if al == 0 else round(100-(100/(1+ag/al)), 2)

def sideways(candles):
    if len(candles) < 10: return False
    hi = [c["high"] for c in candles[-10:]]
    lo = [c["low"]  for c in candles[-10:]]
    cl = [c["close"] for c in candles[-10:]]
    rng = max(hi) - min(lo)
    avg = sum(cl) / len(cl)
    return avg > 0 and rng/avg < 0.0015

def get_pattern(candles):
    if len(candles) < 3: return None, 0
    c = candles
    body = abs(c[-1]["close"] - c[-1]["open"])
    rng  = c[-1]["high"] - c[-1]["low"]
    if rng == 0: return None, 0
    uw = c[-1]["high"] - max(c[-1]["close"], c[-1]["open"])
    lw = min(c[-1]["close"], c[-1]["open"]) - c[-1]["low"]

    if c[-2]["close"]<c[-2]["open"] and c[-1]["close"]>c[-1]["open"] and c[-1]["open"]<c[-2]["close"] and c[-1]["close"]>c[-2]["open"]:
        return "BULLISH ENGULFING", 1
    if c[-2]["close"]>c[-2]["open"] and c[-1]["close"]<c[-1]["open"] and c[-1]["open"]>c[-2]["close"] and c[-1]["close"]<c[-2]["open"]:
        return "BEARISH ENGULFING", -1
    if lw > body*1.5 and uw < body and body > 0: return "HAMMER", 1
    if uw > body*1.5 and lw < body and body > 0: return "SHOOTING STAR", -1
    if lw > rng*0.55: return "BULLISH PIN BAR", 1
    if uw > rng*0.55: return "BEARISH PIN BAR", -1
    if body > rng*0.7:
        return ("MARUBOZU BULL", 1) if c[-1]["close"]>c[-1]["open"] else ("MARUBOZU BEAR", -1)
    if body < rng*0.15:
        if c[-2]["close"]<c[-2]["open"] and c[-3]["close"]<c[-3]["open"]: return "DOJI REVERSAL", 1
        if c[-2]["close"]>c[-2]["open"] and c[-3]["close"]>c[-3]["open"]: return "DOJI REVERSAL", -1
    return None, 0

def analyze(name, m5, m1):
    if not m5 or not m1 or len(m5)<25 or len(m1)<25: return None
    if sideways(m5): return None

    c5 = [c["close"] for c in m5]
    c1 = [c["close"] for c in m1]
    cur = c5[-1]

    e9   = ema(c5, 9);  e21 = ema(c5, 21); e50 = ema(c5, min(50, len(c5)-1))
    e9m  = ema(c1, 9);  e21m = ema(c1, 21)
    r5   = rsi(c5);     r1  = rsi(c1)

    t5 = 1 if e9>e21 else (-1 if e9<e21 else 0)
    t1 = 1 if e9m>e21m else (-1 if e9m<e21m else 0)

    if t5 == 0 or t1 == 0 or t5 != t1: return None
    if 48 <= r5 <= 52: return None
    if t5 == 1 and r5 > 78: return None
    if t5 ==-1 and r5 < 22: return None

    pname, pdir = get_pattern(m1[-5:])
    if not pname: return None
    if pdir != 0 and pdir != t5: return None

    w = learning["weights"]
    score = 0.0; expl = []

    if t5==1 and e9>e21>e50:
        score += w["ema_stack"]; expl.append("EMA bullish stack 9>21>50")
    elif t5==-1 and e9<e21<e50:
        score += w["ema_stack"]; expl.append("EMA bearish stack 9<21<50")
    else:
        score += w["ema_partial"]; expl.append("EMA alinhado")

    if t5==1 and r5<=45: score += w["rsi_strong"]; expl.append(f"RSI sobrevendido {r5:.0f}")
    elif t5==-1 and r5>=55: score += w["rsi_strong"]; expl.append(f"RSI sobrecomprado {r5:.0f}")
    elif t5==1 and r5<=55: score += w["rsi_mild"]; expl.append(f"RSI favoravel {r5:.0f}")
    elif t5==-1 and r5>=45: score += w["rsi_mild"]; expl.append(f"RSI favoravel {r5:.0f}")

    score += w["pattern"]; expl.append(f"Padrao: {pname}")

    hi = [c["high"] for c in m5[-20:]]; lo = [c["low"] for c in m5[-20:]]
    ar = sum(h-l for h,l in zip(hi,lo)) / len(hi)
    if ar > 0:
        if t5==1 and (cur-min(lo)) < ar*2.5: score += w["sr_zone"]; expl.append("Proximo ao suporte")
        elif t5==-1 and (max(hi)-cur) < ar*2.5: score += w["sr_zone"]; expl.append("Proximo a resistencia")

    vols = [c["volume"] for c in m1[-20:]]
    avgv = sum(vols[:-1]) / max(len(vols)-1, 1)
    if avgv > 0 and vols[-1] > avgv*1.2: score += w["volume"]; expl.append("Volume alto")

    if score < 4.0:
        print(f"  {name}: score {score:.1f} insuficiente")
        return None

    grade, awr = asset_grade(name)
    if grade == "D": return None

    conf = round(min(55 + (score/7.0)*41, 96), 1)
    if grade=="A": conf=min(conf+3,96); expl.append(f"Nota A {awr}% WR")
    elif grade=="B": conf=min(conf+1,96)

    return {
        "asset": name, "direction": "CALL" if t5==1 else "PUT",
        "timeframe": "M1+M5", "confidence": conf,
        "confluence_score": round(score,1),
        "entry_price": round(cur,6), "expiry": "5 minutos",
        "expiry_seconds": 300,
        "explanation": ["✓ "+e for e in expl],
        "quality": "EXCELENTE" if score>=6.0 else "BOM",
        "rsi": r5, "pattern": pname, "asset_grade": grade,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
    }

state = {"signals":[], "last_scan":None, "scan_count":0, "scanning":False, "blocked_reason":"", "last_results":[]}
next_scan_time = [time.time() + 5]

def run_scan():
    state["scanning"] = True
    check_reset()

    if credits_today["count"] >= MAX_CREDITS:
        state.update({"scanning":False, "blocked_reason":f"Limite diario atingido ({credits_today['count']}/{MAX_CREDITS}). Renova meia-noite UTC.", "last_scan":datetime.now(timezone.utc).strftime("%H:%M UTC")})
        state["scan_count"] += 1
        return

    bh, reason = bad_hour()
    if bh:
        state.update({"scanning":False, "blocked_reason":reason, "last_scan":datetime.now(timezone.utc).strftime("%H:%M UTC")})
        state["scan_count"] += 1
        print(f"Bloqueado: {reason}")
        return

    state["blocked_reason"] = ""
    signals = []; results = []

    for asset in ASSETS:
        name = asset["symbol"]
        try:
            grade, _ = asset_grade(name)
            if grade == "D":
                results.append({"asset":name,"status":"BLOQUEADO nota D"})
                continue

            print(f"  {name} M5...")
            m5 = fetch(name, "5min")
            time.sleep(REQ_DELAY)
            print(f"  {name} M1...")
            m1 = fetch(name, "1min")
            time.sleep(REQ_DELAY)

            if not m5 or not m1:
                results.append({"asset":name,"status":"SEM DADOS"})
                continue

            sig = analyze(name, m5, m1)
            if sig:
                signals.append(sig)
                results.append({"asset":name,"status":f"SINAL {sig['direction']} {sig['confluence_score']}"})
                print(f"  SINAL: {name} {sig['direction']} score={sig['confluence_score']}")
            else:
                results.append({"asset":name,"status":"Sem confluencia"})
        except Exception as e:
            print(f"  Erro {name}: {e}")
            results.append({"asset":name,"status":f"ERRO: {e}"})

    signals.sort(key=lambda s: s["confluence_score"], reverse=True)
    state["signals"]     = signals[:5]
    state["last_scan"]   = datetime.now(timezone.utc).strftime("%H:%M UTC")
    state["scan_count"] += 1
    state["scanning"]    = False
    state["last_results"] = results
    print(f"Scan #{state['scan_count']} | {len(signals)} sinais | creditos: {credits_today['count']}/{MAX_CREDITS}")

def scanner_loop():
    print("NEXUS AI v6 iniciando em 5s...")
    time.sleep(5)
    while True:
        next_scan_time[0] = time.time() + SCAN_INTERVAL
        print(f"\n--- Scan #{state['scan_count']+1} | creditos: {credits_today['count']}/{MAX_CREDITS} ---")
        try:
            run_scan()
        except Exception as e:
            print(f"Erro: {e}")
            state["scanning"] = False
        print(f"Proximo scan em {SCAN_INTERVAL//60} min")
        time.sleep(SCAN_INTERVAL)


HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>NEXUS AI</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#030a14;--bg2:#071422;--bg3:#0a1c30;--green:#00e5a0;--red:#ff3d6b;--gold:#f5c842;--purple:#7b2fff;--text:#c8d8e8;--muted:#3a5060}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh}
header{background:rgba(3,10,20,.97);border-bottom:1px solid rgba(123,47,255,.2);padding:14px 16px;position:sticky;top:0;z-index:99;display:flex;align-items:center;justify-content:space-between}
.logo{display:flex;align-items:center}
.logo-icon{width:38px;height:38px;background:linear-gradient(135deg,#7b2fff,#00e5a0);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-right:10px}
.logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:17px}
.logo-text span{color:var(--green)}
.live-badge{display:flex;align-items:center;gap:6px;background:rgba(0,229,160,.08);border:1px solid rgba(0,229,160,.2);border-radius:20px;padding:5px 12px;font-size:10px;color:var(--green)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 1.5s infinite}
.scanbar{background:var(--bg2);border-bottom:1px solid rgba(123,47,255,.15);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;font-size:11px}
.progress{height:3px;background:var(--bg3);overflow:hidden}
.prog-inner{height:100%;width:30%;background:linear-gradient(90deg,transparent,var(--purple),var(--green),transparent);animation:scan 2.5s linear infinite}
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid rgba(123,47,255,.15);overflow-x:auto}
.tab{flex:1;padding:12px 6px;text-align:center;font-size:10px;font-family:'Syne',sans-serif;color:var(--muted);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;white-space:nowrap;font-weight:700}
.tab.active{color:var(--green);border-bottom-color:var(--green)}
.content{padding:16px;max-width:480px;margin:0 auto}
.page{display:none}.page.active{display:block}
.card{background:var(--bg2);border:1px solid rgba(123,47,255,.2);border-radius:14px;padding:18px;margin-bottom:14px;position:relative;overflow:hidden;animation:fadeIn .4s ease}
.card.call{border-color:rgba(0,229,160,.35)}.card.put{border-color:rgba(255,61,107,.35)}
.glow{position:absolute;top:0;left:0;right:0;height:1px}
.card.call .glow{background:linear-gradient(90deg,transparent,rgba(0,229,160,.9),transparent)}
.card.put .glow{background:linear-gradient(90deg,transparent,rgba(255,61,107,.9),transparent)}
.sig-hdr{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px}
.dbadge{display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:700;margin-bottom:6px}
.cb{background:rgba(0,229,160,.12);border:1px solid rgba(0,229,160,.4);color:var(--green)}
.pb{background:rgba(255,61,107,.12);border:1px solid rgba(255,61,107,.4);color:var(--red)}
.aname{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:#e8f0f8}
.asub{font-size:10px;color:var(--muted);margin-top:2px}
.conf{font-family:'Syne',sans-serif;font-size:32px;font-weight:800;line-height:1;text-align:right}
.clbl{font-size:9px;color:var(--muted);letter-spacing:.1em;margin-top:3px;text-align:right}
.s3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.sbox{background:rgba(3,10,20,.7);border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:10px 8px;text-align:center}
.sv{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:#e8f0f8}
.sl{font-size:8px;color:var(--muted);margin-top:3px;letter-spacing:.1em}
.expl{font-size:11px;color:#7a9ab0;padding:5px 10px;margin-bottom:4px;border-left:2px solid rgba(0,229,160,.25);background:rgba(0,229,160,.02);border-radius:0 6px 6px 0}
.prow{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid rgba(255,255,255,.05);margin-bottom:10px}
.tbar{background:rgba(3,10,20,.7);border:1px solid rgba(255,255,255,.05);border-radius:8px;padding:8px 12px;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between}
.tval{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:var(--gold)}
.ttrack{flex:1;height:4px;background:var(--bg);border-radius:2px;overflow:hidden;margin:0 10px}
.tfill{height:100%;background:linear-gradient(90deg,var(--red),var(--gold),var(--green));border-radius:2px;transition:width 1s linear}
.btnc{width:100%;padding:14px;background:linear-gradient(135deg,#00c882,#00e5a0);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#030a14;cursor:pointer;box-shadow:0 4px 20px rgba(0,229,160,.3);margin-bottom:8px}
.btnp{width:100%;padding:14px;background:linear-gradient(135deg,#cc1a44,#ff3d6b);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#fff;cursor:pointer;box-shadow:0 4px 20px rgba(255,61,107,.3);margin-bottom:8px}
.orrow{display:flex;gap:8px}
.bw{flex:1;padding:10px;background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.3);border-radius:8px;color:var(--green);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer}
.bl{flex:1;padding:10px;background:rgba(255,61,107,.1);border:1px solid rgba(255,61,107,.3);border-radius:8px;color:var(--red);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer}
.empty{text-align:center;padding:50px 20px;color:var(--muted);font-size:13px}
.empty .icon{font-size:48px;margin-bottom:16px}
.spin{animation:spin 1.5s linear infinite;display:inline-block}
.hrow{display:grid;grid-template-columns:1fr 55px 55px 60px;padding:12px 14px;font-size:11px;align-items:center;background:var(--bg2);border-radius:8px;margin-bottom:6px}
.wb{background:rgba(0,229,160,.1);color:var(--green);border:1px solid rgba(0,229,160,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center}
.lb{background:rgba(255,61,107,.1);color:var(--red);border:1px solid rgba(255,61,107,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center}
.pcard{background:var(--bg2);border:1px solid rgba(123,47,255,.2);border-radius:12px;padding:16px;margin-bottom:12px}
.ptitle{font-size:9px;color:var(--muted);letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px}
.bigstat{font-family:'Syne',sans-serif;font-size:42px;font-weight:800;line-height:1}
.hgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin-top:10px}
.hbox{background:var(--bg3);border-radius:6px;padding:6px 2px;text-align:center}
.hbox.good{background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.2)}
.hbox.bad{background:rgba(255,61,107,.08);border:1px solid rgba(255,61,107,.15)}
.blocked{background:rgba(255,61,107,.06);border:1px solid rgba(255,61,107,.25);border-radius:10px;padding:12px 16px;margin-bottom:14px;font-size:11px;color:#ff6b8a;text-align:center}
.alert{background:rgba(245,200,66,.06);border:1px solid rgba(245,200,66,.25);border-radius:10px;padding:12px 16px;margin-bottom:14px;font-size:11px;color:#c8a020}
.cbar{background:rgba(0,229,160,.04);border:1px solid rgba(0,229,160,.15);border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:10px}
.cbar-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.cbar-fill{height:5px;background:var(--bg3);border-radius:3px;overflow:hidden}
.cbar-inner{height:100%;border-radius:3px;transition:width .5s}
.rrow{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:10px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes scan{0%{transform:translateX(-200%)}100%{transform:translateX(600%)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">&#x26A1;</div>
    <div>
      <div class="logo-text">NEXUS<span>&#xB7;AI</span></div>
      <div style="font-size:9px;color:var(--muted);letter-spacing:.1em">M1+M5 &#xB7; 10 ATIVOS &#xB7; DADOS REAIS</div>
    </div>
  </div>
  <div class="live-badge"><div class="dot"></div>LIVE</div>
</header>
<div class="scanbar">
  <span id="scan-status" style="color:var(--muted)">Iniciando...</span>
  <span id="scan-count" style="color:var(--purple)">0 scans</span>
</div>
<div class="progress"><div class="prog-inner"></div></div>
<div class="tabs">
  <button class="tab active" onclick="showTab('signals',this)">&#x26A1; SINAIS</button>
  <button class="tab" onclick="showTab('history',this)">&#x1F4CB; HISTORICO</button>
  <button class="tab" onclick="showTab('perf',this)">&#x1F4CA; STATS</button>
  <button class="tab" onclick="showTab('assets',this)">&#x1F3C6; ATIVOS</button>
</div>
<div class="content">
  <div id="page-signals" class="page active">
    <div id="credits-bar"></div>
    <div id="sc">
      <div class="empty">
        <div class="icon"><span class="spin">&#x26A1;</span></div>
        <div style="font-family:'Syne',sans-serif;font-size:16px;color:#e8f0f8;margin-bottom:8px">Iniciando NEXUS AI...</div>
        <div>Aguarde o primeiro scan (20 min)</div>
      </div>
    </div>
  </div>
  <div id="page-history" class="page"><div id="hc"><div class="empty"><div class="icon">&#x1F4CB;</div><div>Nenhum trade</div></div></div></div>
  <div id="page-perf" class="page">
    <div class="pcard"><div class="ptitle">Win Rate Geral</div><div class="bigstat" id="wr" style="color:var(--green)">--</div><div style="font-size:11px;color:var(--muted);margin-top:6px" id="ptotal">0 trades</div></div>
    <div class="s3">
      <div class="sbox"><div class="sv" id="pw" style="color:var(--green)">0</div><div class="sl">WINS</div></div>
      <div class="sbox"><div class="sv" id="pl" style="color:var(--red)">0</div><div class="sl">LOSSES</div></div>
      <div class="sbox"><div class="sv" id="ps" style="color:var(--purple)">0</div><div class="sl">SCANS</div></div>
    </div>
    <div class="pcard" id="scan-results-card"><div class="ptitle">Ultimo Scan - Resultado por Ativo</div><div id="scan-results" style="font-size:11px;color:var(--muted)">Aguardando primeiro scan...</div></div>
    <div class="pcard"><div class="ptitle">Win Rate por Horario UTC</div><div class="hgrid" id="hgrid"></div></div>
  </div>
  <div id="page-assets" class="page"><div class="pcard"><div class="ptitle">Ranking de Ativos</div><div id="ar"><div style="font-size:11px;color:var(--muted)">Registre trades para ver o ranking.</div></div></div></div>
</div>
<script>
var history_=JSON.parse(localStorage.getItem('nx_h')||'[]');
var stats=JSON.parse(localStorage.getItem('nx_s')||'{"w":0,"l":0}');
var hourStats=JSON.parse(localStorage.getItem('nx_hs')||'{}');
var assetStats=JSON.parse(localStorage.getItem('nx_as')||'{}');
var prevSigs=[];var timers={};

function showTab(t,el){
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active')});
  document.getElementById('page-'+t).classList.add('active');el.classList.add('active');
  if(t==='perf'){updatePerf();renderHGrid();}
  if(t==='history')renderHistory();
  if(t==='assets')renderAssets();
}

function cc(v){return v>=85?'#00e5a0':v>=72?'#f5c842':'#ff9a3c';}

function beep(){
  try{
    var ctx=new(window.AudioContext||window.webkitAudioContext)();
    var o=ctx.createOscillator(),g=ctx.createGain();
    o.connect(g);g.connect(ctx.destination);
    o.frequency.setValueAtTime(880,ctx.currentTime);
    o.frequency.setValueAtTime(1100,ctx.currentTime+0.1);
    o.frequency.setValueAtTime(880,ctx.currentTime+0.2);
    g.gain.setValueAtTime(0.3,ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+0.5);
    o.start();o.stop(ctx.currentTime+0.5);
  }catch(e){}
}

function startTimer(i,secs,iso){
  if(timers[i])clearInterval(timers[i]);
  var end=(iso?new Date(iso).getTime():Date.now())+secs*1000;
  timers[i]=setInterval(function(){
    var rem=Math.max(0,Math.floor((end-Date.now())/1000));
    var f=document.getElementById('tf-'+i),v=document.getElementById('tv-'+i);
    if(!f||!v){clearInterval(timers[i]);return;}
    f.style.width=(rem/secs*100)+'%';
    v.textContent=Math.floor(rem/60)+':'+(rem%60).toString().padStart(2,'0');
    if(rem===0){clearInterval(timers[i]);v.textContent='EXPIROU';v.style.color='#ff3d6b';}
  },1000);
}

function renderCreditsBar(used,max,nextIn){
  var pct=Math.min(used/max*100,100);
  var col=pct<60?'var(--green)':pct<85?'var(--gold)':'var(--red)';
  var mins=Math.max(0,Math.ceil(nextIn/60));
  var cb=document.getElementById('credits-bar');
  if(cb)cb.innerHTML='<div class="cbar"><div class="cbar-row"><span style="color:var(--muted)">Creditos hoje</span><span style="color:'+col+';font-weight:700">'+used+' / '+max+'</span></div><div class="cbar-fill"><div class="cbar-inner" style="width:'+pct+'%;background:'+col+'"></div></div><div style="margin-top:6px;color:var(--muted)">Proximo scan: <span style="color:var(--purple);font-weight:700">'+mins+' min</span> &nbsp;|&nbsp; Scan a cada <span style="color:var(--muted)">20 min</span></div></div>';
}

function renderScanResults(results){
  var el=document.getElementById('scan-results');
  if(!el||!results||!results.length)return;
  var html='';
  results.forEach(function(r){
    var c=r.status.includes('SINAL')?'var(--green)':r.status.includes('ERRO')||r.status.includes('SEM')||r.status.includes('BLOQUEADO')?'var(--red)':'var(--muted)';
    html+='<div class="rrow"><span style="color:#e8f0f8">'+r.asset+'</span><span style="color:'+c+'">'+r.status+'</span></div>';
  });
  el.innerHTML=html;
}

function renderSignals(data){
  var used=data.credits_used||0;
  var max=data.max_credits||780;
  var nextIn=data.next_scan_in||1200;
  renderCreditsBar(used,max,nextIn);

  var scanEl=document.getElementById('scan-status');
  scanEl.textContent=data.scanning?'Escaneando...':data.blocked_reason?data.blocked_reason:'Ultimo: '+(data.last_scan||'--');
  document.getElementById('scan-count').textContent=data.scan_count+' scans';
  document.getElementById('ps').textContent=data.scan_count;

  if(data.last_results&&data.last_results.length) renderScanResults(data.last_results);

  var c=document.getElementById('sc');

  if(data.blocked_reason){
    c.innerHTML='<div class="blocked">'+data.blocked_reason+'</div><div class="empty"><div class="icon">&#x1F550;</div><div style="font-family:\'Syne\',sans-serif;font-size:14px;color:#e8f0f8;margin-bottom:8px">Melhor: 06h-17h UTC</div><div>(09h-20h Brasilia)</div></div>';
    return;
  }

  if(!data.signals||!data.signals.length){
    var mins=Math.max(1,Math.ceil(nextIn/60));
    c.innerHTML='<div class="empty"><div class="icon">&#x1F50D;</div><div style="font-family:\'Syne\',sans-serif;font-size:15px;color:#e8f0f8;margin-bottom:8px">Nenhum sinal agora</div><div>Proximo scan em '+mins+' min</div><div style="margin-top:10px;font-size:10px;color:var(--muted)">Ultimo: '+(data.last_scan||'--')+'</div></div>';
    return;
  }

  var newKey=data.signals.map(function(s){return s.asset+s.direction;}).join(',');
  var oldKey=prevSigs.map(function(s){return s.asset+s.direction;}).join(',');
  if(newKey!==oldKey&&prevSigs.length>0)beep();
  prevSigs=data.signals;

  var hasEx=data.signals.some(function(s){return s.quality==='EXCELENTE';});
  var html=hasEx?'<div class="alert">&#x2B50; Sinal EXCELENTE detectado!</div>':'';

  data.signals.forEach(function(s,i){
    var isC=s.direction==='CALL';
    var gc=s.asset_grade==='A'?'#00e5a0':s.asset_grade==='B'?'#3d9eff':s.asset_grade==='C'?'#f5c842':'#888';
    html+='<div class="card '+(isC?'call':'put')+'" id="sig-'+i+'"><div class="glow"></div>';
    html+='<div class="sig-hdr"><div><div class="'+(isC?'cb':'pb')+' dbadge">'+(isC?'&#x25B2;':'&#x25BC;')+' '+s.direction+'</div>';
    html+='<div class="aname">'+s.asset+'</div>';
    html+='<div class="asub">'+s.timeframe+' &middot; '+s.expiry+' &middot; <span style="color:'+gc+'">Nota '+s.asset_grade+'</span></div></div>';
    html+='<div><div class="conf" style="color:'+cc(s.confidence)+'">'+s.confidence+'%</div><div class="clbl">CONFIANCA</div></div></div>';
    html+='<div class="tbar"><span style="font-size:9px;color:var(--muted)">EXPIRA EM</span><div class="ttrack"><div class="tfill" id="tf-'+i+'" style="width:100%"></div></div><div class="tval" id="tv-'+i+'">5:00</div></div>';
    html+='<div class="s3"><div class="sbox"><div class="sv">'+s.confluence_score+'</div><div class="sl">SCORE</div></div>';
    html+='<div class="sbox"><div class="sv" style="font-size:11px;color:'+(s.quality==='EXCELENTE'?'#f5c842':'#00e5a0')+'">'+s.quality+'</div><div class="sl">QUALIDADE</div></div>';
    html+='<div class="sbox"><div class="sv" style="font-size:10px">'+s.timestamp+'</div><div class="sl">HORA</div></div></div>';
    html+='<div style="margin-bottom:14px">'+(s.explanation||[]).map(function(e){return '<div class="expl">'+e+'</div>';}).join('')+'</div>';
    html+='<div class="prow"><span style="font-size:10px;color:var(--muted)">Entrada</span><span style="font-size:12px;font-weight:700;color:#e8f0f8">'+s.entry_price+'</span></div>';
    html+='<button class="'+(isC?'btnc':'btnp')+'">ABRIR '+s.direction+' &rarr; '+s.asset+'</button>';
    html+='<div class="orrow"><button class="bw" onclick="rec('+i+',\'WIN\',\''+s.asset+'\',\''+s.direction+'\','+s.confidence+',\''+s.pattern+'\')">&#x2713; WIN</button>';
    html+='<button class="bl" onclick="rec('+i+',\'LOSS\',\''+s.asset+'\',\''+s.direction+'\','+s.confidence+',\''+s.pattern+'\')">&#x2717; LOSS</button></div></div>';
  });

  c.innerHTML=html;
  data.signals.forEach(function(s,i){startTimer(i,s.expiry_seconds||300,s.timestamp_iso);});
}

function rec(i,o,a,d,cf,pat){
  var w=o==='WIN';
  history_.unshift({asset:a,direction:d,confidence:cf,outcome:o,pattern:pat,time:new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})});
  if(history_.length>200)history_.pop();
  localStorage.setItem('nx_h',JSON.stringify(history_));
  if(w)stats.w++;else stats.l++;
  localStorage.setItem('nx_s',JSON.stringify(stats));
  var h=new Date().getUTCHours().toString();
  if(!hourStats[h])hourStats[h]={w:0,l:0};
  if(w)hourStats[h].w++;else hourStats[h].l++;
  localStorage.setItem('nx_hs',JSON.stringify(hourStats));
  if(!assetStats[a])assetStats[a]={w:0,l:0};
  if(w)assetStats[a].w++;else assetStats[a].l++;
  localStorage.setItem('nx_as',JSON.stringify(assetStats));
  fetch('/api/outcome',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({outcome:o,asset:a,pattern:pat,confidence:cf})}).catch(function(){});
  var card=document.getElementById('sig-'+i);
  if(card){card.style.borderColor=w?'#00e5a0':'#ff3d6b';card.style.background='rgba('+(w?'0,229,160':'255,61,107')+',.05)';}
  updatePerf();
  alert((w?'WIN':'LOSS')+' registrado: '+a);
}

function renderHistory(){
  var c=document.getElementById('hc');
  if(!history_.length){c.innerHTML='<div class="empty"><div class="icon">&#x1F4CB;</div><div>Nenhum trade</div></div>';return;}
  var html='<div style="display:grid;grid-template-columns:1fr 55px 55px 60px;padding:8px 14px;font-size:9px;color:var(--muted);margin-bottom:4px"><span>ATIVO</span><span>DIR.</span><span>HORA</span><span>RES.</span></div>';
  history_.slice(0,50).forEach(function(h){
    html+='<div class="hrow"><div><div style="color:#e8f0f8;font-weight:700">'+h.asset+'</div><div style="font-size:9px;color:var(--muted)">'+h.confidence+'%</div></div>';
    html+='<div style="color:'+(h.direction==='CALL'?'#00e5a0':'#ff3d6b')+';font-weight:700">'+(h.direction==='CALL'?'&#x25B2;':'&#x25BC;')+'</div>';
    html+='<div style="color:var(--muted);font-size:10px">'+h.time+'</div>';
    html+='<div class="'+(h.outcome==='WIN'?'wb':'lb')+'">'+h.outcome+'</div></div>';
  });
  c.innerHTML=html;
}

function updatePerf(){
  var t=stats.w+stats.l;
  var wr=t>0?((stats.w/t)*100).toFixed(1)+'%':'--';
  var el=document.getElementById('wr');
  el.textContent=wr;el.style.color=parseFloat(wr)>=60?'#00e5a0':'#ff3d6b';
  document.getElementById('ptotal').textContent=t+' trades';
  document.getElementById('pw').textContent=stats.w;
  document.getElementById('pl').textContent=stats.l;
}

function renderHGrid(){
  var g=document.getElementById('hgrid');if(!g)return;var html='';
  for(var h=0;h<24;h++){
    var hs=hourStats[h.toString()];var t=hs?hs.w+hs.l:0;
    var wr=t>=3?Math.round(hs.w/t*100):null;
    var cls=wr===null?'':wr>=60?'good':wr<45?'bad':'';
    var col=wr===null?'var(--muted)':wr>=60?'var(--green)':wr<45?'var(--red)':'var(--gold)';
    html+='<div class="hbox '+cls+'"><div style="font-size:9px;color:'+col+'">'+h+'h</div>'+(wr!==null?'<div style="font-size:10px;font-weight:700;color:'+col+'">'+wr+'%</div>':'')+'</div>';
  }g.innerHTML=html;
}

function renderAssets(){
  var c=document.getElementById('ar');if(!c)return;
  var list=Object.entries(assetStats).map(function(e){var s=e[0],v=e[1];var t=v.w+v.l;var wr=t>0?Math.round(v.w/t*100):0;var g=wr>=70?'A':wr>=60?'B':wr>=50?'C':'D';return{s:s,t:t,wr:wr,g:g};}).filter(function(a){return a.t>=2;}).sort(function(a,b){return b.wr-a.wr;});
  if(!list.length){c.innerHTML='<div style="font-size:11px;color:var(--muted)">Registre trades para ver.</div>';return;}
  var html='';
  list.forEach(function(a,i){
    var col=a.g==='A'?'#00e5a0':a.g==='B'?'#3d9eff':a.g==='C'?'#f5c842':'#ff3d6b';
    html+='<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)"><div><span style="font-size:12px;color:#e8f0f8;font-weight:700">'+(i+1)+'. '+a.s+'</span><span style="font-size:10px;color:var(--muted);margin-left:8px">'+a.t+' trades</span></div><div><span style="font-size:16px;font-weight:800;color:'+col+'">'+a.wr+'%</span><span style="font-size:11px;color:'+col+';margin-left:6px;font-weight:700">Nota '+a.g+'</span></div></div>';
  });c.innerHTML=html;
}

function fetchSignals(){
  fetch('/api/signals').then(function(r){return r.json();}).then(function(d){renderSignals(d);}).catch(function(){document.getElementById('scan-status').textContent='Reconectando...';});
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
def api_signals():
    next_in = max(0, int(next_scan_time[0] - time.time()))
    return jsonify({
        "signals":        state["signals"],
        "last_scan":      state["last_scan"],
        "scan_count":     state["scan_count"],
        "scanning":       state["scanning"],
        "blocked_reason": state["blocked_reason"],
        "credits_used":   credits_today["count"],
        "max_credits":    MAX_CREDITS,
        "next_scan_in":   next_in,
        "total_assets":   len(ASSETS),
        "last_results":   state["last_results"],
    })

@app.route("/api/outcome", methods=["POST"])
def api_outcome():
    data = request.json or {}
    if data.get("outcome") in ["WIN", "LOSS"]:
        record_learning(data, data["outcome"])
    return jsonify({"status": "ok"})

@app.route("/ping")
def ping():
    return "pong", 200

threading.Thread(target=scanner_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
