
"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, BrainCircuit, CandlestickChart, Gauge, KeyRound, Play, Power, RefreshCcw, ShieldCheck, Wallet } from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type DashboardPayload = any;

async function fetchJson(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  return response.json();
}

function MetricCard({ title, value, sub }: { title: string; value: string | number; sub?: string }) {
  return (
    <div className="metric-card">
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
      {sub ? <div className="metric-sub">{sub}</div> : null}
    </div>
  );
}

function Sparkline({ points }: { points: { equity: number }[] }) {
  const path = useMemo(() => {
    if (!points?.length) return "";
    const values = points.map((p) => Number(p.equity || 0));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = Math.max(1, max - min);
    return values
      .map((value, index) => {
        const x = (index / Math.max(1, values.length - 1)) * 100;
        const y = 100 - ((value - min) / spread) * 100;
        return `${index === 0 ? "M" : "L"}${x},${y}`;
      })
      .join(" ");
  }, [points]);

  return (
    <svg viewBox="0 0 100 100" className="sparkline">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function TradingDashboard() {
  const [tab, setTab] = useState<"binary" | "futures">("binary");
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [testnet, setTestnet] = useState(true);
  const [botConfig, setBotConfig] = useState({
    symbol: "BTCUSDT",
    timeframe: "1min",
    strategy: "institutional_confluence",
    executionMode: "paper",
    maxTradesPerDay: 6,
  });

  const refresh = async () => {
    setLoading(true);
    try {
      const [dashboardRes, logsRes] = await Promise.all([
        fetchJson("/api/v1/system/dashboard"),
        fetchJson("/api/v1/system/logs"),
      ]);
      setDashboard(dashboardRes.data);
      setLogs(logsRes.lines || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, []);

  const binary = dashboard?.binary?.latest;
  const futures = dashboard?.futures?.latest;
  const futuresSummary = dashboard?.futures?.summary || {};
  const binarySummary = dashboard?.binary?.summary || {};
  const analytics = dashboard?.analytics || {};
  const connection = dashboard?.futures?.connection || {};
  const botState = dashboard?.futures?.bot || {};
  const account = dashboard?.futures?.account || {};

  const connectApi = async () => {
    await fetchJson("/api/v1/futures/connect", {
      method: "POST",
      body: JSON.stringify({ apiKey, secretKey, testnet }),
    });
    setApiKey("");
    setSecretKey("");
    refresh();
  };

  const disconnectApi = async () => {
    await fetchJson("/api/v1/futures/disconnect", { method: "POST" });
    refresh();
  };

  const startBot = async () => {
    await fetchJson("/api/v1/futures/bot/start", {
      method: "POST",
      body: JSON.stringify(botConfig),
    });
    refresh();
  };

  const stopBot = async () => {
    await fetchJson("/api/v1/futures/bot/stop", { method: "POST" });
    refresh();
  };

  const runBinaryScan = async () => {
    await fetchJson("/api/v1/binary/analyze");
    refresh();
  };

  const runFuturesScan = async () => {
    const params = new URLSearchParams({
      asset: botConfig.symbol,
      timeframe: botConfig.timeframe,
      strategy: botConfig.strategy,
    });
    await fetchJson(`/api/v1/futures/analyze?${params.toString()}`);
    refresh();
  };

  return (
    <main className="page-shell">
      <section className="header-card">
        <div>
          <div className="eyebrow">Alpha Hive Platform</div>
          <h1>Hybrid Trading Desk</h1>
          <p>Binary Options signal intelligence + Binance Futures execution with adaptive risk control.</p>
        </div>
        <div className="header-actions">
          <button className="ghost-button" onClick={refresh}><RefreshCcw size={16} /> Refresh</button>
          <div className={`mode-pill ${dashboard?.active_mode === "FUTURES_MODE" ? "hot" : "cold"}`}>{dashboard?.active_mode || "BINARY_MODE"}</div>
        </div>
      </section>

      <section className="tabs-row">
        <button className={tab === "binary" ? "tab active" : "tab"} onClick={() => setTab("binary")}><CandlestickChart size={16} /> Binary Options</button>
        <button className={tab === "futures" ? "tab active" : "tab"} onClick={() => setTab("futures")}><Bot size={16} /> Binance Futures</button>
      </section>

      {tab === "binary" ? (
        <section className="grid binary-grid">
          <article className="panel-card hero-panel">
            <div className="panel-title"><CandlestickChart size={18} /> Signal Engine</div>
            <div className="signal-hero">
              <div>
                <div className="signal-asset">{binary?.asset || "No signal yet"}</div>
                <div className={`signal-badge ${(binary?.signal || "WAIT").toLowerCase()}`}>{binary?.signal || "WAIT"}</div>
              </div>
              <button className="primary-button" onClick={runBinaryScan}><Activity size={16} /> Analyze now</button>
            </div>
            <div className="metric-grid">
              <MetricCard title="Expiration" value={binary?.expiration || "M1"} />
              <MetricCard title="Confidence" value={`${binary?.confidence || 0}%`} />
              <MetricCard title="Market condition" value={binary?.market_condition || binary?.regime || "—"} />
              <MetricCard title="Signal score" value={binary?.score || 0} />
            </div>
            <div className="reason-box">
              <h3>Setup explanation</h3>
              <ul>
                {(binary?.reason || ["No binary explanation available yet"]).slice(0, 6).map((line: string, idx: number) => <li key={idx}>{line}</li>)}
              </ul>
            </div>
          </article>

          <article className="panel-card">
            <div className="panel-title"><BrainCircuit size={18} /> Binary Performance</div>
            <div className="metric-grid compact">
              <MetricCard title="Win rate" value={`${binarySummary.winrate || 0}%`} />
              <MetricCard title="Profit factor" value={binarySummary.profit_factor || 0} />
              <MetricCard title="Drawdown" value={`${binarySummary.drawdown_pct || 0}%`} />
              <MetricCard title="Recent trades" value={binarySummary.recent?.total || 0} />
            </div>
            <div className="reason-box">
              <h3>Discipline rules</h3>
              <ul>
                <li>Signals only. No broker execution from this tab.</li>
                <li>Preserves the legacy binary logic and output style.</li>
                <li>Adaptive engine only tightens or relaxes thresholds conservatively.</li>
              </ul>
            </div>
          </article>
        </section>
      ) : (
        <section className="grid futures-grid">
          <article className="panel-card">
            <div className="panel-title"><KeyRound size={18} /> API Panel</div>
            <div className="form-grid">
              <input placeholder="API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              <input placeholder="Secret Key" value={secretKey} onChange={(e) => setSecretKey(e.target.value)} type="password" />
            </div>
            <label className="switch-row">
              <input type="checkbox" checked={testnet} onChange={(e) => setTestnet(e.target.checked)} />
              <span>Use Binance testnet</span>
            </label>
            <div className="button-row">
              <button className="primary-button" onClick={connectApi}><KeyRound size={16} /> Connect</button>
              <button className="ghost-button" onClick={disconnectApi}><Power size={16} /> Disconnect</button>
            </div>
            <div className="status-box">
              <div>Status: <strong>{connection.connected ? "Connected" : "Disconnected"}</strong></div>
              <div>Key: {connection.api_key_masked || "—"}</div>
              <div>Ping: {connection.ping?.ok ? "OK" : connection.ping?.error || "Not checked"}</div>
            </div>
          </article>

          <article className="panel-card">
            <div className="panel-title"><Gauge size={18} /> Trading Control</div>
            <div className="form-grid triple">
              <select value={botConfig.symbol} onChange={(e) => setBotConfig((s) => ({ ...s, symbol: e.target.value }))}>
                {['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT'].map((symbol) => <option key={symbol}>{symbol}</option>)}
              </select>
              <select value={botConfig.timeframe} onChange={(e) => setBotConfig((s) => ({ ...s, timeframe: e.target.value }))}>
                {['1min','5min'].map((tf) => <option key={tf}>{tf}</option>)}
              </select>
              <select value={botConfig.strategy} onChange={(e) => setBotConfig((s) => ({ ...s, strategy: e.target.value }))}>
                {['institutional_confluence','adaptive_momentum'].map((strategy) => <option key={strategy}>{strategy}</option>)}
              </select>
              <select value={botConfig.executionMode} onChange={(e) => setBotConfig((s) => ({ ...s, executionMode: e.target.value }))}>
                {['paper','live'].map((mode) => <option key={mode}>{mode}</option>)}
              </select>
              <input type="number" min={1} max={20} value={botConfig.maxTradesPerDay} onChange={(e) => setBotConfig((s) => ({ ...s, maxTradesPerDay: Number(e.target.value) }))} />
              <button className="ghost-button" onClick={runFuturesScan}><Activity size={16} /> Analyze</button>
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={startBot}><Play size={16} /> Start bot</button>
              <button className="ghost-button" onClick={stopBot}><Power size={16} /> Stop bot</button>
            </div>
            <div className="status-box">
              <div>Bot state: <strong>{botState.running ? "Running" : "Stopped"}</strong></div>
              <div>Daily trades: {botState.daily_trade_count || 0}</div>
              <div>Last error: {botState.last_error || "—"}</div>
            </div>
          </article>

          <article className="panel-card wide">
            <div className="panel-title"><Bot size={18} /> Execution Engine</div>
            <div className="metric-grid compact">
              <MetricCard title="Direction" value={futures?.direction || "—"} />
              <MetricCard title="Entry" value={futures?.entry || "—"} />
              <MetricCard title="Stop Loss" value={futures?.stop_loss || "—"} />
              <MetricCard title="Risk/Reward" value={futures?.risk_reward || "—"} />
              <MetricCard title="Leverage" value={futures?.leverage || "—"} />
              <MetricCard title="Confidence" value={`${futures?.confidence || 0}%`} />
            </div>
            <div className="reason-box">
              <h3>Setup explanation</h3>
              <ul>
                {(futures?.reason || ["No futures plan generated yet"]).slice(0, 8).map((line: string, idx: number) => <li key={idx}>{line}</li>)}
              </ul>
            </div>
          </article>

          <article className="panel-card">
            <div className="panel-title"><Wallet size={18} /> Live Trading Panel</div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Symbol</th><th>Entry</th><th>PnL</th><th>Liq.</th></tr></thead>
                <tbody>
                  {(account.positions || []).filter((row: any) => Number(row.positionAmt || 0) !== 0).slice(0, 10).map((row: any) => (
                    <tr key={`${row.symbol}-${row.positionSide}`}>
                      <td>{row.symbol}</td>
                      <td>{row.entryPrice}</td>
                      <td>{row.unRealizedProfit}</td>
                      <td>{row.liquidationPrice}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="panel-card">
            <div className="panel-title"><ShieldCheck size={18} /> Open Orders</div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Symbol</th><th>Type</th><th>Side</th><th>Status</th></tr></thead>
                <tbody>
                  {(account.open_orders || []).slice(0, 12).map((row: any) => (
                    <tr key={row.orderId}>
                      <td>{row.symbol}</td>
                      <td>{row.type}</td>
                      <td>{row.side}</td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="panel-card wide">
            <div className="panel-title"><BrainCircuit size={18} /> Analytics</div>
            <div className="metric-grid compact">
              <MetricCard title="Win rate" value={`${futuresSummary.winrate || 0}%`} />
              <MetricCard title="Profit factor" value={futuresSummary.profit_factor || 0} />
              <MetricCard title="Drawdown" value={`${futuresSummary.drawdown_pct || 0}%`} />
              <MetricCard title="Tracked trades" value={dashboard?.analytics?.summary?.tracked_trades || 0} />
            </div>
            <div className="chart-card">
              <Sparkline points={analytics.equity_curve || []} />
            </div>
          </article>

          <article className="panel-card wide">
            <div className="panel-title"><Activity size={18} /> Log Panel</div>
            <div className="log-box">
              {logs.slice(-80).map((line, idx) => <div key={idx}>{line}</div>)}
            </div>
          </article>
        </section>
      )}

      {loading ? <div className="loading-pill">Updating desk…</div> : null}
    </main>
  );
}
