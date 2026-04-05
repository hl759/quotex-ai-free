
# Alpha Hive Hybrid Trading Platform

This platform extends the existing Binary Options AI into a dual-engine stack:

- **Binary Options signal engine** for manual execution only
- **Binance Futures execution engine** for paper/live automation
- **Adaptive self-optimization engine** shared across both modes
- **Flask API backend** for control, analytics, and secure exchange access
- **Next.js dashboard** for operators and risk oversight

## What stayed intact

The original binary intelligence was preserved instead of replaced:

- existing `decision_engine.py`
- existing `signal_engine.py`
- existing adaptive / memory / specialist logic
- existing self-optimization journal layer

## What was added

- `core/` runtime and logging layer
- `services/` exchange client, vault, execution orchestration, bot loop
- `api/` Flask route layer for dashboard consumption
- `ui/` Next.js operator dashboard
- `docker-compose.yml` and Dockerfiles for local deployment

## Step-by-step local setup

### 1) Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run_platform.py
```

Backend API default: `http://localhost:8000`

### 2) Frontend

```bash
cd ui
npm install
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Frontend default: `http://localhost:3000`

## Docker deployment locally

```bash
cp .env.example .env
docker compose up --build
```

## API integration guide

### Health and dashboard

- `GET /api/v1/system/health`
- `GET /api/v1/system/dashboard`
- `GET /api/v1/system/logs`

### Binary signal engine

- `GET /api/v1/binary/analyze`

### Binance Futures control

- `POST /api/v1/futures/connect`
- `POST /api/v1/futures/disconnect`
- `GET /api/v1/futures/connection`
- `GET /api/v1/futures/analyze?asset=BTCUSDT&timeframe=1min&strategy=institutional_confluence`
- `POST /api/v1/futures/execute`
- `GET /api/v1/futures/account?symbol=BTCUSDT`
- `GET /api/v1/futures/orders/open?symbol=BTCUSDT`
- `GET /api/v1/futures/orders/history?symbol=BTCUSDT`
- `POST /api/v1/futures/bot/start`
- `POST /api/v1/futures/bot/stop`
- `GET /api/v1/futures/bot/status`
- `POST /api/v1/futures/close-report`

## Deploy guidance

### Backend

Run the Flask API behind Gunicorn or another process manager:

```bash
gunicorn -w 2 -b 0.0.0.0:8000 api.server:app
```

### Frontend

Build the Next.js app and deploy separately:

```bash
cd ui
npm install
npm run build
npm run start
```

### Production notes

- prefer **environment variables or a secret manager** for Binance keys
- use **testnet first** until execution paths are fully validated
- move the futures bot loop into a dedicated worker service when scaling
- keep `paper` mode as the default execution mode

## Future improvements

- websocket user-data stream for lower-latency position tracking
- Redis / Postgres event bus for API-worker separation
- encrypted secret storage backed by a cloud KMS
- more advanced execution tactics: post-only entries, order amend logic, slippage control
- portfolio-level correlation filter and symbol clustering


## GitHub + Render deployment

This repository is now prepared for a **GitHub-connected Render deployment**.

### Recommended Render topology

Use **two Render services from the same GitHub repo**:

1. **Backend Web Service**
   - Root directory: repository root
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:$PORT api.server:app`

2. **Frontend Web Service**
   - Root directory: `ui`
   - Build command: `npm install && npm run build`
   - Start command: `npm run start`

You can create both manually in Render, or let Render read the included `render.yaml` blueprint from the repo root.

### Important Render notes

- **Do not rely on Render ephemeral filesystem** for long-term state. This project already supports `ALPHA_HIVE_DATABASE_URL` for Postgres and `ALPHA_HIVE_DATA_DIR` for a mounted disk.
- For production, prefer:
  - **Render Postgres** for state, trade journal, scan history, and analytics persistence
  - **Render Disk** for any residual local files and logs
- Keep Binance execution in **testnet / paper mode first**.

### Minimum backend environment variables on Render

- `ALLOWED_ORIGINS=https://your-frontend.onrender.com`
- `ALPHA_HIVE_DATABASE_URL=<Render Postgres Internal URL>`
- `ALPHA_HIVE_DATA_DIR=/var/data/alpha_hive`
- `TWELVE_API_KEY_1=...`
- `FINNHUB_API_KEY=...` or `ALPHA_VANTAGE_API_KEY=...`
- `BINANCE_FUTURES_TESTNET=1`
- `BINANCE_FUTURES_EXECUTION_MODE=paper`
- `BINANCE_FUTURES_AUTO_EXECUTION=0`
- `BINANCE_FUTURES_API_KEY=...`
- `BINANCE_FUTURES_API_SECRET=...`

### Minimum frontend environment variable on Render

- `NEXT_PUBLIC_API_BASE_URL=https://your-backend.onrender.com`

### GitHub workflow

1. Push the full repository to GitHub.
2. In Render, create services from the GitHub repo.
3. Either:
   - use the included `render.yaml`, or
   - create the backend and frontend services manually.
4. Add environment variables in Render.
5. Deploy backend first, then point the frontend to the backend URL.
6. Test `/api/v1/system/health` before enabling any futures execution path.

### Safe production rollout sequence

1. Deploy backend + frontend
2. Validate binary signals UI
3. Validate futures analysis endpoints
4. Connect Binance **testnet** only
5. Run `paper` execution mode
6. Review logs, journal, drawdown controls, and order behavior
7. Only then consider enabling live execution
