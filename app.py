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
signal_history = []
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
            box-shadow:0 8px 20px rgba(17,223,197,.18);
            font-size:26px;
            flex-shrink:0;
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
        }

        .tabs{
            display:grid;
            grid-template-columns:repeat(4,1fr);
            gap:10px;
            margin-top:14px;
        }

        .tab-btn{
            text-align:center;
            padding:13px 8px;
            border-radius:16px;
            background:rgba(8,22,38,.86);
            border:1px solid rgba(145,92,255,.08);
            color:var(--muted);
            font-weight:800;
            font-size:13px;
            cursor:pointer;
            transition:.2s ease;
        }

        .tab-btn.active{
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
        }

        .section-sub{
            color:var(--muted);
            font-size:13px;
        }

        .panel{
            display:none;
        }

        .panel.active{
            display:block;
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
        }

        .direction{
            padding:9px 14px;
            border-radius:999px;
            font-weight:900;
            font-size:13px;
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
            white-space:pre-wrap;
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

        .history-list{
            display:flex;
            flex-direction:column;
            gap:10px;
        }

        .history-item{
            background:#08192c;
            border:1px solid rgba(35,215,255,.06);
            border-radius:16px;
            padding:12px;
        }

        .history-top{
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:10px;
            margin-bottom:8px;
        }

        .history-asset{
            font-weight:800;
            font-size:16px;
        }

        .history-meta{
            color:var(--muted);
            font-size:13px;
            line-height:1.45;
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
                <button class="tab-btn active" onclick="showTab('signals', this)">⚡ SINAIS</button>
                <button class="tab-btn" onclick="showTab('history', this)">📋 HISTÓRICO</button>
                <button class="tab-btn" onclick="showTab('stats', this)">📊 STATS</button>
                <button class="tab-btn" onclick="showTab('assets', this)">🏆 ATIVOS</button>
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

        <div id="signals" class="section panel active">
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
                                    <div class="mini-label">Confiança</div>
                                    <div class="mini-value">{{ s.confidence }}%</div>
                                </div>
                                <div class="mini-card">
                                    <div class="mini-label">Timeframe</div>
                                    <div class="mini-value">{{ s.timeframe }}</div>
                                </div>
                                <div class="mini-card">
                                    <div class="mini-label">Entrada</div>
                                    <div class="mini-value">{{ s.entry_time }}</div>
                                </div>
                                <div class="mini-card">
                                    <div class="mini-label">Expiração</div>
                                    <div class="mini-value">{{ s.expiration }}</div>
                                </div>
                                <div class="mini-card">
                                    <div class="mini-label">Status</div>
                                    <div class="mini-value">Ativo</div>
                                </div>
                            </div>

                            <div class="reason-box"><strong>Motivo:</strong>\n{{ s.reason_text }}</div>
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

        <div id="history" class="section panel">
            <div class="section-title">
                <h2>Histórico recente</h2>
                <div class="section-sub">Últimos sinais gerados</div>
            </div>

            {% if history %}
                <div class="history-list">
                    {% for h in history %}
                        <div class="history-item">
                            <div class="history-top">
                                <div class="history-asset">{{ h.asset }}</div>
                                <div class="direction {{ 'call' if h.signal == 'CALL' else 'put' }}">{{ h.signal }}</div>
                            </div>
                            <div class="history-meta">
                                Horário: {{ h.generated_at }}<br>
                                Entrada: {{ h.entry_time }}<br>
                                Expiração: {{ h.expiration }}<br>
                                Score: {{ h.score }} · Confiança: {{ h.confidence }}%
                            </div>
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <div class="empty">
                    <div class="empty-icon">📋</div>
                    <div class="empty-title">Sem histórico ainda</div>
                    <div class="empty-text">Os sinais gerados vão aparecer aqui.</div>
                </div>
            {% endif %}
        </div>

        <div id="stats" class="section panel">
            <div class="section-title">
                <h2>Estatísticas</h2>
                <div class="section-sub">Visão geral do motor</div>
            </div>

            <div class="stats-grid">
                <div class="stats-card">
            
