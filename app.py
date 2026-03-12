"""
Quotex AI Signal Engine — Versão Gratuita
Backend leve com Flask + Twelve Data API
Funciona no Render.com gratuito
"""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests
import numpy as np
import time
import threading
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ─── Configurações ───────────────────────────
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")
SCAN_INTERVAL = 120  # segundos entre cada scan

# Ativos para monitorar (forex + cripto)
ASSETS = [
    # Forex
    {"symbol": "EUR/USD", "type": "forex"},
    {"symbol": "GBP/USD", "type": "forex"},
    {"symbol": "USD/JPY", "type": "forex"},
    {"symbol": "AUD/USD", "type": "forex"},
    {"symbol": "USD/CAD", "type": "forex"},
    {"symbol": "GBP/JPY", "type": "forex"},
    {"symbol": "EUR/GBP", "type": "forex"},
    {"symbol": "EUR/JPY", "type": "forex"},
    # Cripto
    {"symbol": "BTC/USD", "type": "crypto"},
    {"symbol": "ETH/USD", "type": "crypto"},
    {"symbol": "LTC/USD", "type": "crypto"},
]

# Estado global
state = {
    "signals": [],
    "last_scan": None,
    "scan_count": 0,
    "total_wins": 0,
    "total_losses": 0,
    "scanning": False,
}


# ─── Buscar candles da Twelve Data ───────────
def fetch_candles(symbol, interval="5min", outputsize=100):
    """Busca candles reais da Twelve Data API"""
    try:
        # Twelve Data usa formato diferente para cripto
        sym = symbol.replace("/", "")
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
        print(f"Erro ao buscar {symbol}: {e}")
        return None


# ─── Indicadores ─────────────────────────────
def ema(closes, period):
    if len(closes) < period:
        return closes[-1]
    alpha = 2.0 / (period + 1)
    val = closes[0]
    for c in closes[1:]:
        val = alpha * c + (1 - alpha) * val
    return val


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def bollinger(closes, period=20, std=2):
    if len(closes) < period:
        return closes[-1], closes[-1], closes[-1]
    window = closes[-period:]
    mid = np.mean(window)
    sd = np.std(window)
    return mid + std * sd, mid, mid - std * sd


def atr(candles, period=14):
    if len(candles) < period + 1:
        return 0.001
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return np.mean(trs[-period:])


def macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return 0, 0, 0
    closes = np.array(closes)
    ema_fast = np.array([ema(closes[:i+1], fast) for i in range(len(closes))])
    ema_slow = np.array([ema(closes[:i+1], slow) for i in range(len(closes))])
    macd_line = ema_fast - ema_slow
    signal_line = np.array([ema(macd_line[:i+1], signal) for i in range(len(macd_line))])
    hist = macd_line - signal_line
    return float(macd_line[-1]), float(signal_line[-1]), float(hist[-1])


# ─── Análise de Price Action ──────────────────
def detect_pattern(candles):
    if len(candles) < 3:
        return None, 0

    c = candles
    body = abs(c[-1]["close"] - c[-1]["open"])
    rng = c[-1]["high"] - c[-1]["low"]
    upper_wick = c[-1]["high"] - max(c[-1]["close"], c[-1]["open"])
    lower_wick = min(c[-1]["close"], c[-1]["open"]) - c[-1]["low"]
    atr_val = atr(candles)

    # Bullish Engulfing
    if (c[-2]["close"] < c[-2]["open"] and
            c[-1]["close"] > c[-1]["open"] and
            c[-1]["open"] < c[-2]["close"] and
            c[-1]["close"] > c[-2]["open"]):
        return "BULLISH ENGULFING", 1

    # Bearish Engulfing
    if (c[-2]["close"] > c[-2]["open"] and
            c[-1]["close"] < c[-1]["open"] and
            c[-1]["open"] > c[-2]["close"] and
            c[-1]["close"] < c[-2]["open"]):
        return "BEARISH ENGULFING", -1

    # Martelo (Hammer)
    if lower_wick > body * 2 and upper_wick < body * 0.5 and rng > atr_val * 0.5:
        return "HAMMER", 1

    # Estrela Cadente
    if upper_wick > body * 2 and lower_wick < body * 0.5 and rng > atr_val * 0.5:
        return "SHOOTING STAR", -1

    # Pin Bar Alta
    if lower_wick > rng * 0.6 and rng > atr_val * 0.4:
        return "BULLISH PIN BAR", 1

    # Pin Bar Baixa
    if upper_wick > rng * 0.6 and rng > atr_val * 0.4:
        return "BEARISH PIN BAR", -1

    return None, 0


def find_sr_levels(candles, lookback=50):
    """Detecta suporte e resistência por pivôs"""
    highs = [c["high"] for c in candles[-lookback:]]
    lows = [c["low"] for c in candles[-lookback:]]
    current = candles[-1]["close"]
    atr_val = atr(candles)

    resistances = []
    supports = []

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            resistances.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            supports.append(lows[i])

    nearest_r = min(
        [r for r in resistances if r > current],
        key=lambda x: x - current,
        default=None
    )
    nearest_s = max(
        [s for s in supports if s < current],
        key=lambda x: x,
        default=None
    )

    near_support = nearest_s and abs(current - nearest_s) < atr_val * 0.8
    near_resistance = nearest_r and abs(nearest_r - current) < atr_val * 0.8

    return nearest_s, nearest_r, near_support, near_resistance


# ─── Motor de Confluência ─────────────────────
def analyze_asset(symbol, candles_m5, candles_m1):
    """Análise completa e pontuação de confluência"""
    if not candles_m5 or not candles_m1:
        return None
    if len(candles_m5) < 50 or len(candles_m1) < 50:
        return None

    closes_m5 = np.array([c["close"] for c in candles_m5])
    closes_m1 = np.array([c["close"] for c in candles_m1])
    current_price = closes_m5[-1]

    # ── Indicadores M5 ──
    e9_m5  = ema(closes_m5, 9)
    e21_m5 = ema(closes_m5, 21)
    e50_m5 = ema(closes_m5, 50)
    rsi_m5 = rsi(closes_m5)
    _, _, macd_hist_m5 = macd(closes_m5)
    bb_up, bb_mid, bb_lo = bollinger(closes_m5)
    atr_m5 = atr(candles_m5)

    # ── Indicadores M1 ──
    e9_m1  = ema(closes_m1, 9)
    e21_m1 = ema(closes_m1, 21)
    rsi_m1 = rsi(closes_m1)
    _, _, macd_hist_m1 = macd(closes_m1)

    # ── Tendência ──
    trend_m5 = 1 if e9_m5 > e21_m5 > e50_m5 else (-1 if e9_m5 < e21_m5 < e50_m5 else 0)
    trend_m1 = 1 if e9_m1 > e21_m1 else (-1 if e9_m1 < e21_m1 else 0)

    # ── Gate 1: M1 e M5 alinhados ──
    if trend_m5 == 0 or trend_m1 == 0 or trend_m5 != trend_m1:
        return None

    direction = trend_m5

    # ── Gate 2: RSI não neutro ──
    if 45 <= rsi_m5 <= 55:
        return None

    # ── Gate 3: RSI condizente com direção ──
    if direction == 1 and rsi_m5 > 65:
        return None
    if direction == -1 and rsi_m5 < 35:
        return None

    # ── Padrão de candle ──
    pattern_name, pattern_dir = detect_pattern(candles_m1[-5:])
    if not pattern_name:
        return None

    # ── Gate 4: Padrão alinhado com tendência ──
    if pattern_dir != direction:
        return None

    # ── Suporte e Resistência ──
    s_level, r_level, near_s, near_r = find_sr_levels(candles_m5)

    # ── Pontuação de Confluência ──
    score = 0.0
    explanation = []

    # EMA stack (max 2.0)
    if direction == 1 and e9_m5 > e21_m5 > e50_m5:
        score += 2.0
        explanation.append("✓ EMA bullish stack M5 (9>21>50)")
    elif direction == -1 and e9_m5 < e21_m5 < e50_m5:
        score += 2.0
        explanation.append("✓ EMA bearish stack M5 (9<21<50)")
    else:
        score += 1.0
        explanation.append("✓ Tendência EMA parcial")

    # S/R (max 2.0)
    if direction == 1 and near_s:
        score += 2.0
        explanation.append(f"✓ Preço próximo ao suporte {round(s_level, 5)}")
    elif direction == -1 and near_r:
        score += 2.0
        explanation.append(f"✓ Preço próximo à resistência {round(r_level, 5)}")

    # RSI (max 1.0)
    if direction == 1 and rsi_m5 < 40:
        score += 1.0
        explanation.append(f"✓ RSI sobrevendido {rsi_m5:.1f}")
    elif direction == -1 and rsi_m5 > 60:
        score += 1.0
        explanation.append(f"✓ RSI sobrecomprado {rsi_m5:.1f}")
    else:
        score += 0.5
        explanation.append(f"✓ RSI favorável {rsi_m5:.1f}")

    # Padrão de candle (max 1.5)
    score += 1.5
    explanation.append(f"✓ Padrão: {pattern_name}")

    # MACD (max 1.0)
    if direction == 1 and macd_hist_m5 > 0:
        score += 1.0
        explanation.append("✓ MACD histograma positivo")
    elif direction == -1 and macd_hist_m5 < 0:
        score += 1.0
        explanation.append("✓ MACD histograma negativo")

    # Bollinger (max 1.0)
    bb_pct = (current_price - bb_lo) / (bb_up - bb_lo) if (bb_up - bb_lo) > 0 else 0.5
    if direction == 1 and bb_pct < 0.25:
        score += 1.0
        explanation.append("✓ Preço na banda inferior (BB)")
    elif direction == -1 and bb_pct > 0.75:
        score += 1.0
        explanation.append("✓ Preço na banda superior (BB)")

    # ── Filtro mínimo ──
    if score < 6.5:
        return None

    confidence = round(60 + (score / 9.0) * 37, 1)
    confidence = min(confidence, 96.0)

    return {
        "asset": symbol,
        "direction": "CALL" if direction == 1 else "PUT",
        "timeframe": "M5",
        "confidence": confidence,
        "confluence_score": round(score, 1),
        "entry_price": round(current_price, 6),
        "expiry": "5 minutos",
        "explanation": explanation,
        "quality": "EXCELENTE" if score >= 8.0 else "BOM",
        "rsi": rsi_m5,
        "pattern": pattern_name,
        "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
    }


# ─── Scanner Principal ────────────────────────
def run_scan():
    """Escaneia todos os ativos e atualiza sinais"""
    state["scanning"] = True
    new_signals = []

    for asset in ASSETS:
        symbol = asset["symbol"]
        try:
            # Busca candles M5 e M1
            candles_m5 = fetch_candles(symbol, "5min", 100)
            time.sleep(0.5)  # respeita rate limit
            candles_m1 = fetch_candles(symbol, "1min", 100)
            time.sleep(0.5)

            signal = analyze_asset(symbol, candles_m5, candles_m1)
            if signal:
                new_signals.append(signal)
                print(f"✅ Sinal: {symbol} {signal['direction']} score={signal['confluence_score']}")
        except Exception as e:
            print(f"Erro {symbol}: {e}")

    # Ordena por score
    new_signals.sort(key=lambda s: s["confluence_score"], reverse=True)
    state["signals"] = new_signals[:5]
    state["last_scan"] = datetime.utcnow().strftime("%H:%M:%S UTC")
    state["scan_count"] += 1
    state["scanning"] = False
    print(f"Scan #{state['scan_count']} concluído — {len(new_signals)} sinais")


def scanner_loop():
    """Loop contínuo do scanner em background"""
    while True:
        try:
            run_scan()
        except Exception as e:
            print(f"Erro no scanner: {e}")
        time.sleep(SCAN_INTERVAL)


# ─── API Endpoints ────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/signals")
def get_signals():
    return jsonify({
        "signals": state["signals"],
        "last_scan": state["last_scan"],
        "scan_count": state["scan_count"],
        "scanning": state["scanning"],
        "total_assets": len(ASSETS),
    })


@app.route("/api/stats")
def get_stats():
    total = state["total_wins"] + state["total_losses"]
    win_rate = round(state["total_wins"] / total * 100, 1) if total > 0 else 0
    return jsonify({
        "total_signals": total,
        "wins": state["total_wins"],
        "losses": state["total_losses"],
        "win_rate": win_rate,
    })


@app.route("/api/outcome", methods=["POST"])
def record_outcome():
    data = request.json
    if data.get("outcome") == "WIN":
        state["total_wins"] += 1
    elif data.get("outcome") == "LOSS":
        state["total_losses"] += 1
    return jsonify({"status": "ok"})


@app.route("/ping")
def ping():
    """Endpoint para manter servidor acordado (UptimeRobot)"""
    return "pong", 200


# ─── Inicialização ────────────────────────────
if __name__ == "__main__":
    # Inicia scanner em background
    t = threading.Thread(target=scanner_loop, daemon=True)
    t.start()
    print("🚀 Scanner iniciado em background")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
