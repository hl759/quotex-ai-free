from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
import requests
import numpy as np
import time
import threading
import os
import json
from datetime import datetime, timezone

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

# ─── Sistema de Aprendizado ───────────────────
# Pesos iniciais dos fatores de confluência
DEFAULT_WEIGHTS = {
    "ema_stack":   2.0,
    "ema_partial": 1.0,
    "rsi_strong":  1.0,
    "rsi_mild":    0.5,
    "pattern":     1.5,
    "sr_zone":     1.5,
    "volume":      0.5,
}

# Histórico de resultados por fator/ativo/hora
learning_data = {
    "weights":       dict(DEFAULT_WEIGHTS),
    "asset_stats":   {},   # wins/losses por ativo
    "hour_stats":    {},   # wins/losses por hora UTC
    "pattern_stats": {},   # wins/losses por padrão
    "total_trades":  0,
    "total_wins":    0,
}

def update_weights():
    """Ajusta pesos baseado nos resultados acumulados"""
    w = learning_data["weights"]

    # Ajusta por padrão de candle
    for pattern, stats in learning_data["pattern_stats"].items():
        total = stats["wins"] + stats["losses"]
        if total >= 10:
            win_rate = stats["wins"] / total
            if pattern == "ema_stack":
                w["ema_stack"] = round(1.0 + win_rate * 2.0, 2)
            elif pattern in ["HAMMER", "BULLISH PIN BAR", "BULLISH ENGULFING"]:
                w["pattern"] = round(0.5 + win_rate * 2.0, 2)

    # Limita pesos entre 0.1 e 3.0
    for k in w:
        w[k] = max(0.1, min(3.0, w[k]))

def record_outcome(signal_data, outcome):
    """Registra resultado e atualiza aprendizado"""
    is_win = outcome == "WIN"

    # Stats por ativo
    asset = signal_data.get("asset", "")
    if asset not in learning_data["asset_stats"]:
        learning_data["asset_stats"][asset] = {"wins": 0, "losses": 0}
    if is_win:
        learning_data["asset_stats"][asset]["wins"] += 1
    else:
        learning_data["asset_stats"][asset]["losses"] += 1

    # Stats por hora
    hour = str(datetime.now(timezone.utc).hour)
    if hour not in learning_data["hour_stats"]:
        learning_data["hour_stats"][hour] = {"wins": 0, "losses": 0}
    if is_win:
        learning_data["hour_stats"][hour]["wins"] += 1
    else:
        learning_data["hour_stats"][hour]["losses"] += 1

    # Stats por padrão
    pattern = signal_data.get("pattern", "")
    if pattern:
        if pattern not in learning_data["pattern_stats"]:
            learning_data["pattern_stats"][pattern] = {"wins": 0, "losses": 0}
        if is_win:
            learning_data["pattern_stats"][pattern]["wins"] += 1
        else:
            learning_data["pattern_stats"][pattern]["losses"] += 1

    learning_data["total_trades"] += 1
    if is_win:
        learning_data["total_wins"] += 1

    # Atualiza pesos a cada 10 trades
    if learning_data["total_trades"] % 10 == 0:
        update_weights()

def get_asset_grade(symbol):
    """Retorna nota do ativo baseado no histórico: A B C D"""
    stats = learning_data["asset_stats"].get(symbol)
    if not stats:
        return "NEW", 0
    total = stats["wins"] + stats["losses"]
    if total < 5:
        return "NEW", 0
    wr = stats["wins"] / total * 100
    if wr >= 70: return "A", round(wr, 1)
    if wr >= 60: return "B", round(wr, 1)
    if wr >= 50: return "C", round(wr, 1)
    return "D", round(wr, 1)

def is_bad_hour():
    """Verifica se é horário ruim para operar"""
    hour = datetime.now(timezone.utc).hour
    # Madrugada 00h-05h UTC (21h-02h Brasília) = mercado morto
    if 0 <= hour <= 5:
        return True, "Madrugada — mercado sem volume"
    # Fim de semana
    weekday = datetime.now(timezone.utc).weekday()
    if weekday >= 5:
        return True, "Fim de semana — mercado fechado"
    # Hora ruim baseado no histórico (win rate < 40% com 10+ trades)
    hour_stats = learning_data["hour_stats"].get(str(hour))
    if hour_stats:
        total = hour_stats["wins"] + hour_stats["losses"]
        if total >= 10:
            wr = hour_stats["wins"] / total
            if wr < 0.40:
                return True, f"Histórico ruim nesse horário ({round(wr*100)}% win rate)"
    return False, ""

def is_asset_blocked(symbol):
    """Bloqueia ativo com histórico muito ruim"""
    grade, wr = get_asset_grade(symbol)
    stats = learning_data["asset_stats"].get(symbol, {})
    total = stats.get("wins", 0) + stats.get("losses", 0)
    # Bloqueia só se tiver 10+ trades E win rate abaixo de 40%
    if grade == "D" and total >= 10:
        return True
    return False

# ─── Buscar candles ───────────────────────────
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
                "open":   float(v["open"]),
                "high":   float(v["high"]),
                "low":    float(v["low"]),
                "close":  float(v["close"]),
                "volume": float(v.get("volume", 1)),
                "time":   v["datetime"],
            })
        return candles
    except Exception as e:
        print(f"Erro {symbol}: {e}")
        return None

# ─── Indicadores ─────────────────────────────
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
    gains  = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period-1) + gains[i]) / period
        avg_loss = (avg_loss * (period-1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def is_sideways(candles, lookback=15):
    """Detecta mercado lateral — evita sinais em consolidação"""
    if len(candles) < lookback:
        return False
    highs  = [c["high"]  for c in candles[-lookback:]]
    lows   = [c["low"]   for c in candles[-lookback:]]
    closes = [c["close"] for c in candles[-lookback:]]
    rng    = max(highs) - min(lows)
    avg_c  = sum(closes) / len(closes)
    # Range menor que 0.3% do preço = lateral
    if avg_c > 0 and (rng / avg_c) < 0.003:
        return True
    # Volatilidade muito baixa
    atr_vals = [highs[i] - lows[i] for i in range(len(highs))]
    avg_atr  = sum(atr_vals) / len(atr_vals)
    recent_atr = sum(atr_vals[-3:]) / 3
    if recent_atr < avg_atr * 0.4:
        return True
    return False

def detect_pattern(candles):
    if len(candles) < 2:
        return None, 0
    c = candles
    body       = abs(c[-1]["close"] - c[-1]["open"])
    rng        = c[-1]["high"] - c[-1]["low"]
    if rng == 0: return None, 0
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

# ─── Análise principal ────────────────────────
def analyze_asset(symbol, candles_m5, candles_m1):
    if not candles_m5 or not candles_m1:
        return None
    if len(candles_m5) < 30 or len(candles_m1) < 30:
        return None

    # ── Detector de mercado lateral ──
    if is_sideways(candles_m5):
        return None

    closes_m5 = [c["close"] for c in candles_m5]
    closes_m1 = [c["close"] for c in candles_m1]
    current   = closes_m5[-1]

    e9_m5  = ema(closes_m5, 9)
    e21_m5 = ema(closes_m5, 21)
    e50_m5 = ema(closes_m5, min(50, len(closes_m5)-1))
    e9_m1  = ema(closes_m1, 9)
    e21_m1 = ema(closes_m1, 21)

    rsi_m5 = rsi_calc(closes_m5)

    trend_m5 = 1 if e9_m5 > e21_m5 > e50_m5 else (-1 if e9_m5 < e21_m5 < e50_m5 else 0)
    trend_m1 = 1 if e9_m1 > e21_m1 else (-1 if e9_m1 < e21_m1 else 0)

    # Gates obrigatórios
    if trend_m5 == 0 or trend_m1 == 0 or trend_m5 != trend_m1:
        return None
    if 45 <= rsi_m5 <= 55:
        return None
    if trend_m5 == 1 and rsi_m5 > 65:
        return None
    if trend_m5 == -1 and rsi_m5 < 35:
        return None

    direction    = trend_m5
    pattern_name, pattern_dir = detect_pattern(candles_m1[-5:])
    if not pattern_name or pattern_dir != direction:
        return None

    # ── Pontuação com pesos aprendidos ──
    w     = learning_data["weights"]
    score = 0.0
    explanation = []

    if direction == 1 and e9_m5 > e21_m5 > e50_m5:
        score += w["ema_stack"]
        explanation.append(f"✓ EMA bullish stack M5 (9>21>50)")
    elif direction == -1 and e9_m5 < e21_m5 < e50_m5:
        score += w["ema_stack"]
        explanation.append(f"✓ EMA bearish stack M5 (9<21<50)")
    else:
        score += w["ema_partial"]

    if direction == 1 and rsi_m5 < 42:
        score += w["rsi_strong"]
        explanation.append(f"✓ RSI sobrevendido {rsi_m5:.1f}")
    elif direction == -1 and rsi_m5 > 58:
        score += w["rsi_strong"]
        explanation.append(f"✓ RSI sobrecomprado {rsi_m5:.1f}")
    else:
        score += w["rsi_mild"]
        explanation.append(f"✓ RSI favorável {rsi_m5:.1f}")

    score += w["pattern"]
    explanation.append(f"✓ Padrão: {pattern_name}")

    highs   = [c["high"] for c in candles_m5[-20:]]
    lows    = [c["low"]  for c in candles_m5[-20:]]
    avg_rng = sum(h - l for h, l in zip(highs, lows)) / len(highs)

    if direction == 1 and (current - min(lows)) < avg_rng * 1.5:
        score += w["sr_zone"]
        explanation.append("✓ Próximo ao suporte")
    elif direction == -1 and (max(highs) - current) < avg_rng * 1.5:
        score += w["sr_zone"]
        explanation.append("✓ Próximo à resistência")

    volumes = [c["volume"] for c in candles_m1[-20:]]
    avg_vol = sum(volumes[:-1]) / max(len(volumes)-1, 1)
    if volumes[-1] > avg_vol * 1.5:
        score += w["volume"]
        explanation.append("✓ Volume acima da média")

    if score < 5.5:
        return None

    # Nota do ativo
    grade, asset_wr = get_asset_grade(symbol)
    if grade == "D":
        return None

    confidence = round(min(60 + (score / 7.0) * 37, 96), 1)

    # Boost de confiança para ativos com histórico bom
    if grade == "A":
        confidence = min(confidence + 3, 96)
        explanation.append(f"✓ Ativo nota A ({asset_wr}% win rate histórico)")
    elif grade == "B":
        confidence = min(confidence + 1, 96)

    return {
        "asset":           symbol,
        "direction":       "CALL" if direction == 1 else "PUT",
        "timeframe":       "M5",
        "confidence":      confidence,
        "confluence_score": round(score, 1),
        "entry_price":     round(current, 6),
        "expiry":          "5 minutos",
        "expiry_seconds":  300,
        "explanation":     explanation,
        "quality":         "EXCELENTE" if score >= 6.5 else "BOM",
        "rsi":             rsi_m5,
        "pattern":         pattern_name,
        "asset_grade":     grade,
        "timestamp":       datetime.now(timezone.utc).strftime("%H:%M UTC"),
        "timestamp_iso":   datetime.now(timezone.utc).isoformat(),
    }

# ─── Estado global ────────────────────────────
state = {
    "signals":     [],
    "last_scan":   None,
    "scan_count":  0,
    "scanning":    False,
    "blocked_reason": "",
}

def run_scan():
    state["scanning"] = True

    # Verifica horário
    bad_hour, reason = is_bad_hour()
    if bad_hour:
        state["scanning"]      = False
        state["blocked_reason"] = reason
        state["last_scan"]     = datetime.now(timezone.utc).strftime("%H:%M UTC")
        state["scan_count"]   += 1
        print(f"Scan bloqueado: {reason}")
        return

    state["blocked_reason"] = ""
    new_signals = []

    for asset in ASSETS:
        symbol = asset["symbol"]
        try:
            if is_asset_blocked(symbol):
                print(f"Ativo bloqueado por histórico ruim: {symbol}")
                continue
            candles_m5 = fetch_candles(symbol, "5min", 60)
            time.sleep(0.8)
            candles_m1 = fetch_candles(symbol, "1min", 60)
            time.sleep(0.8)
            signal = analyze_asset(symbol, candles_m5, candles_m1)
            if signal:
                new_signals.append(signal)
                print(f"✅ Sinal: {symbol} {signal['direction']} score={signal['confluence_score']}")
        except Exception as e:
            print(f"Erro {symbol}: {e}")

    new_signals.sort(key=lambda s: s["confluence_score"], reverse=True)
    state["signals"]    = new_signals[:5]
    state["last_scan"]  = datetime.now(timezone.utc).strftime("%H:%M UTC")
    state["scan_count"] += 1
    state["scanning"]   = False
    print(f"Scan #{state['scan_count']} — {len(new_signals)} sinais")

def scanner_loop():
    time.sleep(5)
    while True:
        try:
            run_scan()
        except Exception as e:
            print(f"Erro scanner: {e}")
        time.sleep(120)

# ─── HTML Dashboard ───────────────────────────
HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>⚡ NEXUS AI Signals</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#030a14;--bg2:#071422;--bg3:#0a1c30;--green:#00e5a0;--red:#ff3d6b;--gold:#f5c842;--blue:#3d9eff;--purple:#7b2fff;--text:#c8d8e8;--muted:#3a5060;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;}
header{background:rgba(3,10,20,0.97);border-bottom:1px solid rgba(123,47,255,0.2);padding:14px 16px;position:sticky;top:0;z-index:99;display:flex;align-items:center;justify-content:space-between;}
.logo{display:flex;align-items:center;}
.logo-icon{width:38px;height:38px;background:linear-gradient(135deg,#7b2fff,#00e5a0);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;margin-right:10px;}
.logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:17px;letter-spacing:.05em;}
.logo-text span{color:var(--green);}
.live{display:flex;align-items:center;gap:6px;background:rgba(0,229,160,0.08);border:1px solid rgba(0,229,160,0.2);border-radius:20px;padding:5px 12px;font-size:10px;color:var(--green);letter-spacing:.1em;}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 1.5s infinite;}
.scanbar{background:var(--bg2);border-bottom:1px solid rgba(123,47,255,0.15);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;font-size:11px;}
.progress{height:3px;background:var(--bg3);overflow:hidden;}
.progress-inner{height:100%;width:30%;background:linear-gradient(90deg,transparent,var(--purple),var(--green),transparent);animation:scan 2.5s linear infinite;}
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid rgba(123,47,255,0.15);overflow-x:auto;}
.tab{flex:1;padding:12px 6px;text-align:center;font-size:10px;letter-spacing:.06em;font-family:'Syne',sans-serif;color:var(--muted);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;white-space:nowrap;font-weight:700;}
.tab.active{color:var(--green);border-bottom-color:var(--green);background:rgba(0,229,160,0.04);}
.content{padding:16px;max-width:480px;margin:0 auto;}
.page{display:none;}.page.active{display:block;}
/* Signal card */
.card{background:var(--bg2);border:1px solid rgba(123,47,255,0.2);border-radius:14px;padding:18px;margin-bottom:14px;position:relative;overflow:hidden;animation:fadeIn .4s ease;}
.card.call{border-color:rgba(0,229,160,0.3);}
.card.put{border-color:rgba(255,61,107,0.3);}
.glow{position:absolute;top:0;left:0;right:0;height:1px;}
.card.call .glow{background:linear-gradient(90deg,transparent,rgba(0,229,160,.8),transparent);}
.card.put .glow{background:linear-gradient(90deg,transparent,rgba(255,61,107,.8),transparent);}
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
.price-row{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid rgba(255,255,255,.05);margin-bottom:10px;}
/* Timer */
.timer-bar{background:rgba(3,10,20,.7);border:1px solid rgba(255,255,255,.05);border-radius:8px;padding:8px 12px;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;}
.timer-val{font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:var(--gold);}
.timer-track{flex:1;height:4px;background:var(--bg);border-radius:2px;overflow:hidden;margin:0 10px;}
.timer-fill{height:100%;background:linear-gradient(90deg,var(--red),var(--gold),var(--green));border-radius:2px;transition:width 1s linear;}
/* Buttons */
.btn-c{width:100%;padding:15px;background:linear-gradient(135deg,#00c882,#00e5a0);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#030a14;cursor:pointer;letter-spacing:.05em;box-shadow:0 4px 20px rgba(0,229,160,.3);margin-bottom:8px;}
.btn-p{width:100%;padding:15px;background:linear-gradient(135deg,#cc1a44,#ff3d6b);border:none;border-radius:12px;font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#fff;cursor:pointer;letter-spacing:.05em;box-shadow:0 4px 20px rgba(255,61,107,.3);margin-bottom:8px;}
.outcome-row{display:flex;gap:8px;margin-top:4px;}
.btn-w{flex:1;padding:10px;background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.3);border-radius:8px;color:var(--green);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer;}
.btn-l{flex:1;padding:10px;background:rgba(255,61,107,.1);border:1px solid rgba(255,61,107,.3);border-radius:8px;color:var(--red);font-family:'Syne',sans-serif;font-size:12px;font-weight:700;cursor:pointer;}
/* Empty */
.empty{text-align:center;padding:50px 20px;color:var(--muted);font-size:13px;}
.empty .icon{font-size:48px;margin-bottom:16px;}
.spin{animation:spin 1.5s linear infinite;display:inline-block;}
/* History */
.hrow{display:grid;grid-template-columns:1fr 55px 55px 60px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.03);font-size:11px;align-items:center;background:var(--bg2);border-radius:8px;margin-bottom:6px;}
.wb{background:rgba(0,229,160,.1);color:var(--green);border:1px solid rgba(0,229,160,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center;}
.lb{background:rgba(255,61,107,.1);color:var(--red);border:1px solid rgba(255,61,107,.2);border-radius:5px;padding:2px 7px;font-size:10px;font-weight:700;text-align:center;}
/* Performance */
.pcard{background:var(--bg2);border:1px solid rgba(123,47,255,0.2);border-radius:12px;padding:16px;margin-bottom:12px;}
.ptitle{font-size:9px;color:var(--muted);letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px;}
.bigstat{font-family:'Syne',sans-serif;font-size:42px;font-weight:800;line-height:1;}
/* Asset grades */
.grade-A{color:var(--green);font-weight:700;}
.grade-B{color:var(--blue);font-weight:700;}
.grade-C{color:var(--gold);font-weight:700;}
.grade-D{color:var(--red);font-weight:700;}
.grade-NEW{color:var(--muted);font-weight:700;}
/* Hour chart */
.hour-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin-top:10px;}
.hour-box{background:var(--bg3);border-radius:6px;padding:6px 2px;text-align:center;}
.hour-box.good{background:rgba(0,229,160,.1);border:1px solid rgba(0,229,160,.2);}
.hour-box.bad{background:rgba(255,61,107,.08);border:1px solid rgba(255,61,107,.15);}
/* Alert banner */
.alert-banner{background:rgba(247,200,66,.06);border:1px solid rgba(247,200,66,.25);border-radius:10px;padding:12px 16px;margin-bottom:14px;display:flex;align-items:center;gap:10px;font-size:11px;color:#c8a020;}
.blocked-banner{background:rgba(255,61,107,.06);border:1px solid rgba(255,61,107,.25);border-radius:10px;padding:12px 16px;margin-bottom:14px;font-size:11px;color:#ff6b8a;text-align:center;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes scan{0%{transform:translateX(-200%)}100%{transform:translateX(600%)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes timerPulse{0%,100%{opacity:1}50%{opacity:.6}}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-icon">⚡</div>
    <div>
      <div class="logo-text">NEXUS<span>·AI</span></div>
      <div style="font-size:9px;color:var(--muted);letter-spacing:.1em">M1 + M5 · 20 ATIVOS</div>
    </div>
  </div>
  <div class="live"><div class="dot"></div>LIVE</div>
</header>
<div class="scanbar">
  <span id="scan-status" style="color:var(--muted)">Iniciando scanner...</span>
  <span id="scan-count" style="color:var(--purple)">0 scans</span>
</div>
<div class="progress"><div class="progress-inner"></div></div>
<div class="tabs">
  <button class="tab active" onclick="showTab('signals',this)">⚡ SINAIS</button>
  <button class="tab" onclick="showTab('history',this)">📋 HISTÓRICO</button>
  <button class="tab" onclick="showTab('performance',this)">📊 STATS</button>
  <button class="tab" onclick="showTab('assets',this)">🏆 ATIVOS</button>
</div>
<div class="content">

  <!-- SINAIS -->
  <div id="page-signals" class="page active">
    <div id="signals-container">
      <div class="empty">
        <div class="icon"><span class="spin">⚡</span></div>
        <div style="font-family:'Syne',sans-serif;font-size:16px;color:#e8f0f8;margin-bottom:8px">Iniciando NEXUS AI...</div>
        <div>Escaneando 20 ativos em tempo real</div>
      </div>
    </div>
  </div>

  <!-- HISTÓRICO -->
  <div id="page-history" class="page">
    <div id="history-container">
      <div class="empty"><div class="icon">📋</div><div>Nenhum trade registrado ainda</div></div>
    </div>
  </div>

  <!-- PERFORMANCE -->
  <div id="page-performance" class="page">
    <div class="pcard">
      <div class="ptitle">Win Rate Geral</div>
      <div class="bigstat" id="wr" style="color:var(--green)">—</div>
      <div style="font-size:11px;color:var(--muted);margin-top:6px" id="ptotal">0 trades registrados</div>
    </div>
    <div class="stats3">
      <div class="sbox"><div class="sval" id="pw" style="color:var(--green)">0</div><div class="slbl">WINS</div></div>
      <div class="sbox"><div class="sval" id="pl" style="color:var(--red)">0</div><div class="slbl">LOSSES</div></div>
      <div class="sbox"><div class="sval" id="ps" style="color:var(--purple)">0</div><div class="slbl">SCANS</div></div>
    </div>
    <div class="pcard">
      <div class="ptitle">Melhores Horários (UTC)</div>
      <div class="hour-grid" id="hour-grid"></div>
    </div>
    <div class="pcard">
      <div class="ptitle">Sistema de Aprendizado</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.8" id="learning-info">
        Registre WIN e LOSS nos sinais para o sistema aprender e melhorar automaticamente.
      </div>
    </div>
  </div>

  <!-- ATIVOS -->
  <div id="page-assets" class="page">
    <div class="pcard">
      <div class="ptitle">Ranking de Ativos</div>
      <div id="asset-ranking">
        <div style="font-size:11px;color:var(--muted)">Registre trades para ver o ranking aparecer aqui.</div>
      </div>
    </div>
  </div>

</div>

<audio id="signal-sound" preload="auto">
  <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhS0pjeZ6tnHxgTU5jgqGnk3djV1htjKqrm4FqW1ltja2snYJrXFpwhKaqmoFqWlpwhKaqmoFqWlpwhKaqmoFqWlpwhKaqmoFqWlpwhKaqmoFqWlpwhA==" type="audio/wav">
</audio>

<script>
let history = JSON.parse(localStorage.getItem('nx_h') || '[]');
let stats   = JSON.parse(localStorage.getItem('nx_s') || '{"w":0,"l":0}');
let hourStats = JSON.parse(localStorage.getItem('nx_hs') || '{}');
let assetStats = JSON.parse(localStorage.getItem('nx_as') || '{}');
let activeSignals = [];
let timers = {};

function showTab(t, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + t).classList.add('active');
  el.classList.add('active');
  if (t === 'performance') { updatePerf(); renderHourGrid(); }
  if (t === 'history') renderHistory();
  if (t === 'assets') renderAssets();
}

function cc(v) { return v >= 85 ? '#00e5a0' : v >= 75 ? '#f5c842' : '#ff9a3c'; }

function playAlert() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.2);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch(e) {}
}

function startTimer(idx, expirySeconds, tsIso) {
  if (timers[idx]) clearInterval(timers[idx]);
  const entryTime = tsIso ? new Date(tsIso).getTime() : Date.now();
  const endTime = entryTime + expirySeconds * 1000;

  timers[idx] = setInterval(() => {
    const remaining = Math.max(0, Math.floor((endTime - Date.now()) / 1000));
    const fillEl = document.getElementById(`timer-fill-${idx}`);
    const valEl  = document.getElementById(`timer-val-${idx}`);
    if (!fillEl || !valEl) { clearInterval(timers[idx]); return; }
    const pct = (remaining / expirySeconds) * 100;
    fillEl.style.width = pct + '%';
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    valEl.textContent = `${m}:${s.toString().padStart(2,'0')}`;
    if (remaining === 0) {
      clearInterval(timers[idx]);
      valEl.textContent = 'EXPIROU';
      valEl.style.color = '#ff3d6b';
    }
  }, 1000);
}

function renderSignals(data) {
  const c = document.getElementById('signals-container');
  document.getElementById('scan-status').textContent =
    data.scanning ? '⚡ Escaneando...' :
    data.blocked_reason ? `🔴 ${data.blocked_reason}` :
    `Último: ${data.last_scan || '—'}`;
  document.getElementById('scan-count').textContent = `${data.scan_count} scans`;
  document.getElementById('ps').textContent = data.scan_count;

  if (data.blocked_reason) {
    c.innerHTML = `<div class="blocked-banner">🔴 ${data.blocked_reason}<br><span style="font-size:10px;opacity:.7">Scanner aguardando horário ideal</span></div>
    <div class="empty"><div class="icon">🕐</div><div style="font-family:'Syne',sans-serif;font-size:14px;color:#e8f0f8;margin-bottom:8px">Melhor horário: 06h–17h UTC</div><div style="font-size:11px">(09h–20h horário de Brasília)</div></div>`;
    return;
  }

  if (!data.signals || data.signals.length === 0) {
    c.innerHTML = `<div class="empty"><div class="icon">🔍</div>
    <div style="font-family:'Syne',sans-serif;font-size:15px;color:#e8f0f8;margin-bottom:8px">Nenhum sinal agora</div>
    <div>Analisando ${data.total_assets || 20} ativos.<br>Aguarde o próximo scan.</div>
    <div style="margin-top:12px;font-size:10px;color:var(--muted)">Último scan: ${data.last_scan || '—'}</div></div>`;
    return;
  }

  // Detecta novo sinal
  const newAssets = data.signals.map(s => s.asset + s.direction).join(',');
  const oldAssets = activeSignals.map(s => s.asset + s.direction).join(',');
  if (newAssets !== oldAssets && activeSignals.length > 0) {
    playAlert();
  }
  activeSignals = data.signals;

  // Banner excelente
  const hasExcel = data.signals.some(s => s.quality === 'EXCELENTE');
  let html = hasExcel ? `<div class="alert-banner">⭐ Sinal EXCELENTE detectado — alta probabilidade!</div>` : '';

  data.signals.forEach((s, i) => {
    const isC = s.direction === 'CALL';
    const cf  = cc(s.confidence);
    const gradeColor = s.asset_grade === 'A' ? '#00e5a0' : s.asset_grade === 'B' ? '#3d9eff' : s.asset_grade === 'C' ? '#f5c842' : '#888';

    html += `<div class="card ${isC ? 'call' : 'put'}" id="sig-${i}">
    <div class="glow"></div>
    <div class="sig-header">
      <div>
        <div class="${isC ? 'call-b' : 'put-b'} dir-badge">${isC ? '▲' : '▼'} ${s.direction}</div>
        <div class="asset">${s.asset}</div>
        <div class="asset-sub">${s.timeframe} · ${s.expiry} · <span style="color:${gradeColor}">Nota ${s.asset_grade}</span></div>
      </div>
      <div>
        <div class="conf" style="color:${cf}">${s.confidence}%</div>
        <div class="conf-lbl">CONFIANÇA</div>
      </div>
    </div>
    <div class="timer-bar">
      <span style="font-size:9px;color:var(--muted)">EXPIRA EM</span>
      <div class="timer-track"><div class="timer-fill" id="timer-fill-${i}" style="width:100%"></div></div>
      <div class="timer-val" id="timer-val-${i}">5:00</div>
    </div>
    <div class="stats3">
      <div class="sbox"><div class="sval">${s.confluence_score}</div><div class="slbl">SCORE</div></div>
      <div class="sbox"><div class="sval" style="font-size:11px;color:${s.quality === 'EXCELENTE' ? '#f5c842' : '#00e5a0'}">${s.quality}</div><div class="slbl">QUALIDADE</div></div>
      <div class="sbox"><div class="sval" style="font-size:10px">${s.timestamp}</div><div class="slbl">HORA</div></div>
    </div>
    <div style="margin-bottom:14px">${(s.explanation || []).map(e => `<div class="expl">${e}</div>`).join('')}</div>
    <div class="price-row"><span style="font-size:10px;color:var(--muted)">Preço entrada</span><span style="font-size:12px;font-weight:700;color:#e8f0f8">${s.entry_price}</span></div>
    <button class="${isC ? 'btn-c' : 'btn-p'}">ABRIR ${s.direction} → ${s.asset}</button>
    <div class="outcome-row">
      <button class="btn-w" onclick="rec(${i},'WIN','${s.asset}','${s.direction}',${s.confidence},'${s.pattern}')">✓ WIN</button>
      <button class="btn-l" onclick="rec(${i},'LOSS','${s.asset}','${s.direction}',${s.confidence},'${s.pattern}')">✗ LOSS</button>
    </div></div>`;
  });

  c.innerHTML = html;

  // Inicia timers
  data.signals.forEach((s, i) => {
    startTimer(i, s.expiry_seconds || 300, s.timestamp_iso);
  });
}

function rec(i, o, asset, dir, cf, pattern) {
  const isWin = o === 'WIN';
  history.unshift({ asset, direction: dir, confidence: cf, outcome: o, pattern,
    time: new Date().toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}) });
  if (history.length > 200) history.pop();
  localStorage.setItem('nx_h', JSON.stringify(history));

  if (isWin) stats.w++; else stats.l++;
  localStorage.setItem('nx_s', JSON.stringify(stats));

  // Hour stats
  const h = new Date().getUTCHours().toString();
  if (!hourStats[h]) hourStats[h] = {w:0, l:0};
  if (isWin) hourStats[h].w++; else hourStats[h].l++;
  localStorage.setItem('nx_hs', JSON.stringify(hourStats));

  // Asset stats
  if (!assetStats[asset]) assetStats[asset] = {w:0, l:0};
  if (isWin) assetStats[asset].w++; else assetStats[asset].l++;
  localStorage.setItem('nx_as', JSON.stringify(assetStats));

  fetch('/api/outcome', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({outcome: o, asset, pattern, confidence: cf})
  }).catch(() => {});

  const card = document.getElementById('sig-' + i);
  if (card) {
    card.style.borderColor = isWin ? '#00e5a0' : '#ff3d6b';
    card.style.background = `rgba(${isWin ? '0,229,160' : '255,61,107'},.05)`;
  }
  updatePerf();
  alert(`${isWin ? '✅' : '❌'} ${o} registrado — ${asset}!`);
}

function renderHistory() {
  const c = document.getElementById('history-container');
  if (!history.length) { c.innerHTML = '<div class="empty"><div class="icon">📋</div><div>Nenhum trade registrado</div></div>'; return; }
  let html = `<div style="display:grid;grid-template-columns:1fr 55px 55px 60px;padding:8px 14px;font-size:9px;color:var(--muted);letter-spacing:.08em;margin-bottom:4px"><span>ATIVO</span><span>DIR.</span><span>HORA</span><span>RES.</span></div>`;
  history.slice(0, 50).forEach(h => {
    html += `<div class="hrow"><div><div style="color:#e8f0f8;font-weight:700">${h.asset}</div><div style="font-size:9px;color:var(--muted)">${h.confidence}%</div></div><div style="color:${h.direction==='CALL'?'#00e5a0':'#ff3d6b'};font-weight:700">${h.direction==='CALL'?'▲':'▼'}</div><div style="color:var(--muted);font-size:10px">${h.time}</div><div class="${h.outcome==='WIN'?'wb':'lb'}">${h.outcome}</div></div>`;
  });
  c.innerHTML = html;
}

function updatePerf() {
  const t = stats.w + stats.l;
  const wr = t > 0 ? ((stats.w / t) * 100).toFixed(1) + '%' : '—';
  const wrEl = document.getElementById('wr');
  wrEl.textContent = wr;
  wrEl.style.color = parseFloat(wr) >= 60 ? '#00e5a0' : '#ff3d6b';
  document.getElementById('ptotal').textContent = `${t} trades registrados`;
  document.getElementById('pw').textContent = stats.w;
  document.getElementById('pl').textContent = stats.l;

  // Learning info
  const li = document.getElementById('learning-info');
  if (li && t >= 10) {
    li.innerHTML = `Sistema aprendendo com <strong style="color:#e8f0f8">${t} trades</strong>.<br>
    Pesos ajustados automaticamente.<br>
    Ativos ruins bloqueados automaticamente.`;
  }
}

function renderHourGrid() {
  const grid = document.getElementById('hour-grid');
  if (!grid) return;
  let html = '';
  for (let h = 0; h < 24; h++) {
    const hs = hourStats[h.toString()];
    const total = hs ? hs.w + hs.l : 0;
    const wr = total >= 3 ? Math.round(hs.w / total * 100) : null;
    const cls = wr === null ? '' : wr >= 60 ? 'good' : wr < 45 ? 'bad' : '';
    const color = wr === null ? 'var(--muted)' : wr >= 60 ? 'var(--green)' : wr < 45 ? 'var(--red)' : 'var(--gold)';
    html += `<div class="hour-box ${cls}">
      <div style="font-size:9px;color:${color}">${h}h</div>
      ${wr !== null ? `<div style="font-size:10px;font-weight:700;color:${color}">${wr}%</div>` : ''}
    </div>`;
  }
  grid.innerHTML = html;
}

function renderAssets() {
  const c = document.getElementById('asset-ranking');
  if (!c) return;
  const assets = Object.entries(assetStats)
    .map(([sym, s]) => {
      const t = s.w + s.l;
      const wr = t > 0 ? Math.round(s.w / t * 100) : 0;
      const grade = wr >= 70 ? 'A' : wr >= 60 ? 'B' : wr >= 50 ? 'C' : 'D';
      return { sym, t, wr, grade, w: s.w, l: s.l };
    })
    .filter(a => a.t >= 2)
    .sort((a, b) => b.wr - a.wr);

  if (!assets.length) {
    c.innerHTML = '<div style="font-size:11px;color:var(--muted)">Registre pelo menos 2 trades por ativo para ver o ranking.</div>';
    return;
  }

  let html = '';
  assets.forEach((a, i) => {
    const color = a.grade === 'A' ? '#00e5a0' : a.grade === 'B' ? '#3d9eff' : a.grade === 'C' ? '#f5c842' : '#ff3d6b';
    html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)">
      <div>
        <span style="font-size:12px;color:#e8f0f8;font-weight:700">${i+1}. ${a.sym}</span>
        <span style="font-size:10px;color:var(--muted);margin-left:8px">${a.t} trades</span>
      </div>
      <div style="text-align:right">
        <span style="font-size:16px;font-weight:800;color:${color}">${a.wr}%</span>
        <span style="font-size:11px;color:${color};margin-left:6px;font-weight:700">Nota ${a.grade}</span>
      </div>
    </div>`;
  });
  c.innerHTML = html;
}

async function fetchSignals() {
  try {
    const r = await fetch('/api/signals');
    const d = await r.json();
    renderSignals(d);
  } catch(e) {
    document.getElementById('scan-status').textContent = '⚠ Servidor iniciando...';
  }
}

fetchSignals();
setInterval(fetchSignals, 30000);
updatePerf();
</script>
</body>
</html>"""

# ─── API Endpoints ────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/signals")
def get_signals():
    return jsonify({
        "signals":        state["signals"],
        "last_scan":      state["last_scan"],
        "scan_count":     state["scan_count"],
        "scanning":       state["scanning"],
        "total_assets":   len(ASSETS),
        "blocked_reason": state["blocked_reason"],
    })

@app.route("/api/outcome", methods=["POST"])
def api_outcome():
    data = request.json or {}
    outcome = data.get("outcome", "")
    if outcome in ["WIN", "LOSS"]:
        record_outcome(data, outcome)
    return jsonify({"status": "ok", "weights": learning_data["weights"]})

@app.route("/api/learning")
def api_learning():
    return jsonify({
        "weights":       learning_data["weights"],
        "total_trades":  learning_data["total_trades"],
        "total_wins":    learning_data["total_wins"],
        "asset_stats":   learning_data["asset_stats"],
        "hour_stats":    learning_data["hour_stats"],
        "pattern_stats": learning_data["pattern_stats"],
    })

@app.route("/ping")
def ping():
    return "pong", 200

# ─── Start ────────────────────────────────────
t = threading.Thread(target=scanner_loop, daemon=True)
t.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
