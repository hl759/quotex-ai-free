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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>NEXUS-AI</title>
    <style>
        :root{
            --bg:#030814;
            --bg-soft:#071325;
            --card:#08182a;
            --card-2:#0b1f36;
            --line:rgba(59, 130, 246, .12);
            --line-2:rgba(45, 212, 191, .14);
            --text:#eef4ff;
            --muted:#91a4c3;
            --muted-2:#6f86aa;
            --green:#1df2a4;
            --cyan:#23d7ff;
            --purple:#915cff;
            --yellow:#ffd84d;
            --red:#ff6b7a;
            --shadow:0 12px 34px rgba(0,0,0,.34);
            --radius-xl:24px;
            --radius-lg:18px;
            --radius-md:14px;
        }

        *{
            box-sizing:border-box;
            -webkit-tap-highlight-color: transparent;
        }

        html, body{
            margin:0;
            padding:0;
            background:
                radial-gradient(circle at 15% 0%, rgba(145,92,255,.16), transparent 28%),
                radial-gradient(circle at 100% 0%, rgba(35,215,255,.12), transparent 24%),
                linear-gradient(180deg, #020712 0%, #04101d 42%, #030814 100%);
            color:var(--text);
            font-family: Inter, Arial, Helvetica, sans-serif;
            min-height:100vh;
        }

        .app{
            max-width:720px;
            margin:0 auto;
            padding:14px 14px 28px;
        }

        .hero{
            position:relative;
            overflow:hidden;
            background:linear-gradient(180deg, rgba(6,18,35,.96), rgba(6,18,35,.82));
            border:1px solid rgba(35,215,255,.12);
            border-radius:28px;
            padding:16px;
            box-shadow:var(--shadow);
        }

        .hero::before{
            content:"";
            position:absolute;
            inset:auto -40px -40px auto;
            width:180px;
            height:180px;
            background:radial-gradient(circle, rgba(29,242,164,.12), transparent 60%);
            pointer-events:none;
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
            gap:12px;
            min-width:0;
        }

        .logo{
            width:54px;
            height:54px;
            border-radius:18px;
            display:flex;
            align-items:center;
            justify-content:center;
            background:linear-gradient(135deg, #6f4cff, #11dfc5);
            box-shadow:
                0 0 0 1px rgba(255,255,255,.06),
                0 8px 20px rgba(17,223,197,.18);
            font-size:26px;
            flex-shrink:0;
        }

        .brand-text{
            min-width:0;
        }

        .title{
            font-weight:900;
            font-size:30px;
            line-height:1;
            letter-spacing:.4px;
            white-space:nowrap;
        }

        .title .accent{
            color:var(--green);
        }

        .subtitle{
            margin-top:6px;
            color:var(--muted);
            font-size:12px;
            letter-spacing:2px;
            text-transform:uppercase;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
            max-width:100%;
        }

        .live{
            display:flex;
            align-items:center;
            gap:8px;
            padding:10px 14px;
            border-radius:999px;
            background:rgba(8,32,30,.55);
            border:1px solid rgba(29,242,164,.22);
            color:#9efdda;
            font-weight:800;
            font-size:14px;
            flex-shrink:0;
            box-shadow:inset 0 0 14px rgba(29,242,164,.06);
        }

        .dot{
            width:10px;
            height:10px;
            border-radius:50%;
            background:var(--green);
            box-shadow:0 0 12px var(--green);
        }

        .hero-stats{
            display:grid;
            grid-template-columns:1fr 1fr 1fr;
            gap:10px;
            margin-top:16px;
        }

        .metric{
            background:rgba(10,24,43,.82);
            border:1px solid rgba(35,215,255,.08);
            border-radius:16px;
            padding:12px;
        }

        .metric-label{
            color:var(--muted-2);
            font-size:11px;
            text-transform:uppercase;
            letter-spacing:1px;
            margin-bottom:6px;
        }

        .metric-value{
            font-size:18px;
            font-weight:800;
            color:var(--text);
        }

        .tabs{
            display:grid;
            grid-template-columns:repeat(4,1fr);
            gap:10px;
            margin-top:14px;
        }

        .tab{
            text-align:center;
            padding:13px 8px;
            border-radius:16px;
            background:rgba(8,22,38,.86);
            border:1px solid rgba(145,92,255,.08);
            color:var(--muted);
            font-weight:800;
            font-size:13px;
        }

        .tab.active{
            color:var(--green);
            border-color:rgba(29,242,164,.24);
            box-shadow:inset 0 -3px 0 var(--green);
        }

        .section{
            margin-top:16px;
            background:linear-gradient(180deg, rgba(7,19,37,.94), rgba(6,17,31,.94));
            border:1px solid rgba(35,215,255,.1);
            border-radius:24px;
            padding:16px;
            box-shadow:var(--shadow);
        }

        .section-title{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:10px;
            margin-bottom:14px;
        }

        .section-title h2{
            margin:0;
            font-size:18px;
            letter-spacing:.2px;
        }

        .section-sub{
            color:var(--muted);
            font-size:13px;
        }

        .credits-top{
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:10px;
            margin-bottom:12px;
        }

        .credits-left{
            color:var(--muted);
            font-size:14px;
        }

        .credits-right{
            font-size:24px;
            font-weight:900;
            color:var(--green);
        }

        .progress{
            height:12px;
            background:#0b1930;
            border-radius:999px;
            overflow:hidden;
            border:1px solid rgba(35,215,255,.08);
        }

        .progress-bar{
            height:100%;
            width:{{ credits_percent }}%;
            background:linear-gradient(90deg, #22d3ee, #8b5cf6, #1df2a4);
            box-shadow:0 0 18px rgba(35,215,255,.25);
        }

        .credits-meta{
            margin-top:12px;
            display:flex;
            justify-content:space-between;
            gap:10px;
            color:var(--muted);
            font-size:14px;
            flex-wrap:wrap;
        }

        .credits-meta strong{
            color:var(--purple);
        }

        .empty{
            text-align:center;
            padding:34px 8px 20px;
        }

        .empty-icon{
            font-size:70px;
            margin-bottom:12px;
        }

        .empty-title{
            font-size:20px;
            font-weight:900;
            margin-bottom:8px;
        }

        .empty-text{
            color:var(--muted);
            font-size:15px;
            margin:4px 0;
        }

        .signals{
            display:flex;
            flex-direction:column;
            gap:14px;
        }

        .signal-card{
            background:linear-gradient(180deg, rgba(10,27,47,.98), rgba(7,20,35,.98));
            border:1px solid rgba(35,215,255,.1);
            border-radius:20px;
            padding:15px;
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
            letter-spacing:.2px;
        }

        .direction{
            padding:9px 14px;
            border-radius:999px;
            font-weight:900;
            font-size:13px;
            letter-spacing:.4px;
        }

        .direction.call{
            background:linear-gradient(135deg, #1df2a4, #7dffc8);
            color:#062116;
        }

        .direction.put{
            background:linear-gradient(135deg, #ff7c90, #ffc0c9);
            color:#341017;
        }

        .signal-grid{
            display:grid;
            grid-template-columns:1fr 1fr 1fr;
            gap:10px;
        }

        .mini-card{
            background:#09192b;
            border:1px solid rgba(35,215,255,.06);
            border-radius:14px;
            padding:12px;
        }

        .mini-label{
            color:var(--muted-2);
            font-size:11px;
            text-transform:uppercase;
            letter-spacing:1px;
            margin-bottom:6px;
        }

        .mini-value{
            font-size:17px;
            font-weight:800;
        }

        .reason-box{
            margin-top:12px;
            background:#071423;
            border:1px solid rgba(35,215,255,.06);
            border-radius:14px;
            padding:12px;
            color:#dce7ff;
            line-height:1.45;
            font-size:14px;
            word-break:break-word;
        }

        .stats-grid{
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:12px;
        }

        .stats-card{
            background:linear-gradient(180deg, rgba(9,23,39,.94), rgba(7,18,32,.94));
            border:1px solid rgba(145,92,255,.08);
            border-radius:18px;
            padding:14px;
        }

        .stats-label{
            color:var(--muted);
            font-size:12px;
            text-transform:uppercase;
            letter-spacing:1px;
            margin-bottom:8px;
        }

        .stats-value{
            font-size:24px;
            font-weight:900;
        }

        .accent-green{color:var(--green)}
        .accent-purple{color:var(--purple)}
        .accent-cyan{color:var(--cyan)}
        .accent-yellow{color:var(--yellow)}

        .ranking{
            display:flex;
            flex-direction:column;
            gap:10px;
        }

        .rank-item{
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
            background:#08192c;
            border:1px solid rgba(35,215,255,.06);
            border-radius:16px;
            padding:12px;
        }

        .rank-left{
            display:flex;
            align-items:center;
            gap:12px;
        }

        .rank-num{
            width:32px;
            height:32px;
            border-radius:12px;
            display:flex;
            align-items:center;
            justify-content:center;
            background:linear-gradient(135deg, #8b5cf6, #22d3ee);
            color:white;
            font-weight:900;
            font-size:14px;
        }

        .rank-name{
            font-weight:800;
            font-size:15px;
        }

        .rank-right{
            color:var(--green);
            font-weight:800;
            font-size:14px;
        }

        .footer{
            margin-top:16px;
            text-align:center;
            color:var(--muted);
            font-size:13px;
            padding-bottom:8px;
        }

        @media (max-width:560px){
            .app{padding:12px 12px 28px}
            .title{font-size:26px}
            .subtitle{font-size:11px; letter-spacing:1.4px}
            .hero-stats{grid-template-columns:1fr 1fr}
            .tabs{grid-template-columns:1fr 1fr}
            .signal-grid{grid-template-columns:1fr 1fr}
            .stats-grid{grid-template-columns:1fr}
            .asset{font-size:19px}
            .credits-right{font-size:20px}
        }
    </style>
</head>
<body>
    <div class="app">
        <div class="hero">
            <div class="hero-top">
                <div class="brand">
                    <div class="logo">⚡</div>
                    <div class="brand-text">
                        <div class="title">NEXUS-<span class="accent">AI</span></div>
                        <div class="subtitle">M1 + M5 · {{ asset_count }} ATIVOS · DADOS REAIS</div>
                    </div>
                </div>
                <div class="live">
                    <span class="dot"></span>
                    LIVE
                </div>
            </div>

            <div class="hero-stats">
                <div class="metric">
                    <div class="metric-label">Último scan</div>
                    <div class="metric-value">{{ last_scan if last_scan else '--' }}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total scans</div>
                    <div class="metric-value">{{ scan_count }}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Sinais agora</div>
                    <div class="metric-value">{{ signals|length }}</div>
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
            <div class="section-title">
                <h2>Créditos da Twelve Data</h2>
                <div class="section-sub">Proteção ativa</div>
            </div>

            <div class="credits-top">
                <div class="credits-left">Uso de créditos hoje</div>
                <div class="credits-right">{{ credits_today }} / {{ max_credits }}</div>
            </div>

            <div class="progress">
                <div class="progress-bar"></div>
            </div>

            <div class="credits-meta">
                <div>Próximo scan: <strong>{{ next_scan }}</strong></div>
                <div>Scan a cada <strong>{{ scan_interval }} min</strong></div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">
                <h2>Sinais em tempo real</h2>
                <div class="section-sub">Precisão acima de quantidade</div>
            </div>

            {% if signals %}
                <div class="signals">
                    {% for s in signals %}
                        <div class="signal-card">
                            <div class="signal-head">
                                <div class="asset">{{ s.asset }}</div>
                                <div class="direction {{ 'call' if s.signal == 'CALL' else 'put' }}">{{ s.signal }}</div>
                            </div>

                            <div class="signal-grid">
                                <div class="mini-card">
                                    <div class="mini-label">Score</div>
                                    <div class="mini-value">{{ s.score }}</div>
                                </div>
                                <div class="mini-card">
                                    <div class="mini-label">Timeframe</div>
                                    <div class="mini-value">M1</div>
                                </div>
                                <div class="mini-card">
                                    <div class="mini-label">Status</div>
                                    <div class="mini-value">{{ 'Ativo' if s.signal else 'Aguardando' }}</div>
                                </div>
                            </div>

                            <div class="reason-box">
                                <strong>Motivo:</strong><br>
                                {{ s.reason }}
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <div class="empty">
                    <div class="empty-icon">🔎</div>
                    <div class="empty-title">Nenhum sinal agora</div>
                    <div class="empty-text">Próximo scan em {{ next_scan }}</div>
                    <div class="empty-text">Último scan: {{ last_scan if last_scan else '--' }}</div>
                </div>
            {% endif %}
        </div>

        <div class="stats-grid">
            <div class="section stats-card">
                <div class="stats-label">Win Rate estimado</div>
                <div class="stats-value accent-green">{{ estimated_win_rate }}%</div>
            </div>

            <div class="section stats-card">
                <div class="stats-label">Ativos monitorados</div>
                <div class="stats-value accent-cyan">{{ asset_count }}</div>
            </div>

            <div class="section stats-card">
                <div class="stats-label">Scans executados</div>
                <div class="stats-value accent-purple">{{ scan_count }}</div>
            </div>

            <div class="section stats-card">
                <div class="stats-label">Sinais atuais</div>
                <div class="stats-value accent-yellow">{{ signals|length }}</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">
                <h2>Top ativos</h2>
                <div class="section-sub">Liquidez e relevância</div>
            </div>

            <div class="ranking">
                {% for item in top_assets %}
                    <div class="rank-item">
                        <div class="rank-left">
                            <div class="rank-num">{{ loop.index }}</div>
                            <div class="rank-name">{{ item }}</div>
                        </div>
                        <div class="rank-right">Monitorando</div>
                    </div>
                {% endfor %}
            </div>
        </div>

        <div class="footer">
            Rotas disponíveis: /health · /signals
        </div>
    </div>
</body>
</html>
"""

def scanner_loop():
    global latest_signals, last_scan_time, scan_count

    while True:
        try:
            market_data = scanner.scan_assets()
            signals = signal_engine.generate_signals(market_data)

            latest_signals = signals if signals else []

            if signals:
                learning.update_stats(signals)

            last_scan_time = datetime.now()
            scan_count += 1

            print(f"Scan #{scan_count} | Signals: {len(latest_signals)}", flush=True)

        except Exception as e:
            print(f"Scanner error: {e}", flush=True)

        time.sleep(60)

@app.route("/")
def home():
    credits_today = getattr(data_manager, "credits_today", 0)
    max_credits = 780
    credits_percent = min((credits_today / max_credits) * 100, 100) if max_credits else 0

    if last_scan_time:
        diff = int(time.time() - last_scan_time.timestamp())
        remain = max(60 - diff, 0)
        next_scan = f"{remain}s"
        last_scan = last_scan_time.strftime("%H:%M:%S")
    else:
        next_scan = "60s"
        las
