import threading
import time
from datetime import datetime
from flask import Flask, jsonify, render_template_string

from scanner import MarketScanner
from signal_engine import SignalEngine
from data_manager import DataManager
from learning_engine import LearningEngine
from config import ASSETS

app = Flask(__name__)

data_manager = DataManager()
scanner = MarketScanner(data_manager)
signal_engine = SignalEngine()
learning = LearningEngine()

latest_signals = []
last_scan_time = None
scan_count = 0

HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEXUS-AI</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: linear-gradient(180deg, #020814 0%, #041325 100%);
            color: #ecf3ff;
            font-family: Arial, sans-serif;
        }

        .container {
            max-width: 760px;
            margin: 0 auto;
            padding: 14px;
        }

        .hero {
            background: linear-gradient(180deg, #071728 0%, #081d33 100%);
            border: 1px solid rgba(0,255,200,0.12);
            border-radius: 24px;
            padding: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }

        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo {
            width: 54px;
            height: 54px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            background: linear-gradient(135deg, #7c4dff, #19f0d1);
        }

        .title {
            font-size: 30px;
            font-weight: 900;
            line-height: 1;
        }

        .title span {
            color: #19f0d1;
        }

        .subtitle {
            margin-top: 6px;
            font-size: 12px;
            color: #8ea3c2;
            letter-spacing: 2px;
            text-transform: uppercase;
        }

        .live {
            padding: 10px 14px;
            border-radius: 999px;
            background: rgba(20,60,50,0.45);
            border: 1px solid rgba(25,240,209,0.24);
            color: #9bffe5;
            font-weight: bold;
            font-size: 14px;
            white-space: nowrap;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 14px;
        }

        .stat-card {
            background: #0a1b31;
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 12px;
        }

        .stat-label {
            font-size: 11px;
            color: #7e93b3;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 18px;
            font-weight: bold;
        }

        .tabs {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-top: 14px;
        }

        .tab {
            text-align: center;
            padding: 12px 8px;
            border-radius: 14px;
            background: #08182c;
            color: #89a0c0;
            border: 1px solid rgba(255,255,255,0.05);
            font-size: 13px;
            font-weight: bold;
        }

        .tab.active {
            color: #19f0d1;
            border-color: rgba(25,240,209,0.24);
        }

        .section {
            margin-top: 16px;
            background: linear-gradient(180deg, #071728 0%, #08182d 100%);
            border: 1px solid rgba(0,255,200,0.10);
            border-radius: 22px;
            padding: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.28);
        }

        .section-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 12px;
        }

        .credits-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }

        .credits-value {
            font-size: 24px;
            font-weight: bold;
            color: #19f0d1;
        }

        .bar {
            width: 100%;
            height: 12px;
            background: #0b1930;
            border-radius: 999px;
            overflow: hidden;
        }

        .bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #22d3ee, #8b5cf6, #19f0d1);
        }

        .credits-meta {
            margin-top: 12px;
            font-size: 14px;
            color: #8ea3c2;
        }

        .signal-card {
            background: #0a1c30;
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 18px;
            padding: 14px;
            margin-bottom: 12px;
        }

        .signal-head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }

        .asset {
            font-size: 22px;
            font-weight: bold;
        }

        .badge {
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: bold;
        }

        .call {
            background: linear-gradient(135deg, #19f0a0, #7dffc8);
            color: #062218;
        }

        .put {
            background: linear-gradient(135deg, #ff7b8c, #ffc0c8);
            color: #311016;
        }

        .signal-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }

        .mini {
            background: #09192a;
            border-radius: 14px;
            padding: 12px;
        }

        .mini-label {
            font-size: 11px;
            color: #7e93b3;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .mini-value {
            font-size: 17px;
            font-weight: bold;
        }

        .reason {
            margin-top: 12px;
            background: #061321;
            border-radius: 14px;
            padding: 12px;
            color: #d7e3f8;
            font-size: 14px;
            line-height: 1.45;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .empty {
            text-align: center;
            padding: 34px 12px;
            color: #8ea3c2;
        }

        .empty .icon {
            font-size: 70px;
            margin-bottom: 10px;
        }

        .ranking-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #09192a;
            border-radius: 14px;
            padding: 12px;
            margin-bottom: 10px;
        }

        .ranking-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .rank-num {
            width: 30px;
            height: 30px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #8b5cf6, #22d3ee);
            font-weight: bold;
        }

        .ranking-status {
            color: #19f0d1;
            font-size: 14px;
            font-weight: bold;
        }

        .footer {
            margin-top: 16px;
            text-align: center;
            color: #7e93b3;
            font-size: 13px;
        }

        @media (max-width: 560px) {
            .title {
                font-size: 26px;
            }

            .stats {
                grid-template-columns: repeat(2, 1fr);
            }

            .tabs {
                grid-template-columns: repeat(2, 1fr);
            }

            .signal-grid {
                grid-template-columns: repeat(2, 1fr);
            }

            .asset {
                font-size: 19px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <div class="hero-top">
                <div class="brand">
                    <div class="logo">⚡</div>
                    <div>
                        <div class="title">NEXUS-<span>AI</span></div>
                        <div class="subtitle">M1 + M5 · {{ asset_count }} ativos · dados reais</div>
                    </div>
                </div>
                <div class="live">● LIVE</div>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <div class="stat-label">Último scan</div>
                    <div class="stat-value">{{ last_scan }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Scans</div>
                    <div class="stat-value">{{ scan_count }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Sinais</div>
                    <div class="stat-value">{{ signal_count }}</div>
                </div>
            </div>

            <div class="tabs">
                <div class="tab active">⚡ SINAIS</div>
                <div class="tab">📋 HISTÓRICO</div>
                <div class="tab">📊 STATS</div>
                <div class="tab">🏆 ATIVOS</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Créditos da Twelve Data</div>

            <div class="credits-top">
                <div>Uso de créditos hoje</div>
                <div class="credits-value">{{ credits_today }} / {{ max_credits }}</div>
            </div>

            <div class="bar">
                <div class="bar-fill" style="width: {{ credits_percent }}%;"></div>
            </div>

            <div class="credits-meta">
                Próximo scan: <strong>{{ next_scan }}</strong> · Scan a cada <strong>{{ scan_interval }} min</strong>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Sinais em tempo real</div>

            {% if signals %}
                {% for s in signals %}
                    <div class="signal-card">
                        <div class="signal-head">
                            <div class="asset">{{ s.asset }}</div>
                            <div class="badge {% if s.signal == 'CALL' %}call{% else %}put{% endif %}">
                                {{ s.signal }}
                            </div>
                        </div>

                        <div class="signal-grid">
                            <div class="mini">
                                <div class="mini-label">Score</div>
                                <div class="mini-value">{{ s.score }}</div>
                            </div>
                            <div class="mini">
                                <div class="mini-label">Timeframe</div>
                                <div class="mini-value">M1</div>
                            </div>
                            <div class="mini">
                                <div class="mini-label">Confiança</div>
                                <div class="mini-value">{{ s.confidence }}%</div>
                            </div>
                        </div>

                        <div class="reason">{{ s.reason_text }}</div>
                    </div>
                {% endfor %}
            {% else %}
                <div class="empty">
                    <div class="icon">🔎</div>
                    <div><strong>Nenhum sinal agora</strong></div>
                    <div style="margin-top:8px;">Próximo scan em {{ next_scan }}</div>
                </div>
            {% endif %}
        </div>

        <div class="section">
            <div class="section-title">Top ativos</div>

            {% for item in top_assets %}
                <div class="ranking-item">
                    <div class="ranking-left">
                        <div class="rank-num">{{ loop.index }}</div>
                        <div>{{ item }}</div>
                    </div>
                    <div class="ranking-status">Monitorando</div>
                </div>
            {% endfor %}
        </div>

        <div class="footer">
            Rotas: /health · /signals
        </div>
    </div>
</body>
</html>
"""

def normalize_signals(signals):
    normalized = []

    for s in signals:
        asset = str(s.get("asset", "N/A"))
        signal = str(s.get("signal", "CALL"))
        score = s.get("score", 0)

        try:
            confidence = int(min(max(float(score) * 20, 50), 99))
        except Exception:
            confidence = 50

        reason = s.get("reason", {})
        if isinstance(reason, dict):
            reason_lines = []
            for k, v in reason.items():
                reason_lines.append(f"{k}: {v}")
            reason_text = "\\n".join(reason_lines) if reason_lines else "Sem detalhes"
        else:
            reason_text = str(reason)

        normalized.append({
            "asset": asset,
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "reason_text": reason_text,
        })

    return normalized

def scanner_loop():
    global latest_signals, last_scan_time, scan_count

    while True:
        try:
            market_data = scanner.scan_assets()
            raw_signals = signal_engine.generate_signals(market_data)
            latest_signals = normalize_signals(raw_signals if raw_signals else [])

            if latest_signals:
                learning.update_stats(raw_signals)

            last_scan_time = datetime.now()
            scan_count += 1

            print(f"Scan #{scan_count} | Signals: {len(latest_signals)}", flush=True)

        except Exception as e:
            print(f"Scanner error: {e}", flush=True)

        time.sleep(60)

@app.route("/")
def home():
    credits_today = int(getattr(data_manager, "credits_today", 0))
    max_credits = 780
    credits_percent = int(min((credits_today / max_credits) * 100, 100)) if max_credits else 0

    if last_scan_time:
        diff = int(time.time() - last_scan_time.timestamp())
        remain = max(60 - diff, 0)
        next_scan = f"{remain}s"
        last_scan = last_scan_time.strftime("%H:%M:%S")
    else:
        next_scan = "60s"
        last_scan = "--"

    return render_template_string(
        HTML_PAGE,
        signals=latest_signals,
        credits_today=credits_today,
        max_credits=max_credits,
        credits_percent=credits_percent,
        next_scan=next_scan,
        last_scan=last_scan,
        scan_count=scan_count,
        scan_interval=1,
        asset_count=len(ASSETS),
        signal_count=len(latest_signals),
        top_assets=ASSETS[:5]
    )

@app.route("/health")
def health():
    return {"status": "NEXUS v8 running"}

@app.route("/signals")
def signals():
    return jsonify(latest_signals)

thread = threading.Thread(target=scanner_loop, daemon=True)
thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
