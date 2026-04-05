# Render Deployment Guide

## Repository layout for Render

- Backend service runs from the repository root
- Frontend service runs from `ui/`
- Root `render.yaml` defines both services for Blueprint deploys

## Option A — Blueprint deploy

1. Push this repo to GitHub.
2. In Render, choose **New Blueprint**.
3. Select the repository.
4. Render will detect `render.yaml` and create:
   - `alpha-hive-platform-api`
   - `alpha-hive-platform-ui`
5. Fill in the secret environment variables before the first production run.

## Option B — Manual deploy

### Backend
- Service type: Web Service
- Environment: Python
- Root directory: repo root
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:$PORT api.server:app`
- Health check path: `/api/v1/system/health`

### Frontend
- Service type: Web Service
- Environment: Node
- Root directory: `ui`
- Build command: `npm install && npm run build`
- Start command: `npm run start`

## Recommended Render add-ons

### 1) Persistent Disk
Attach a disk to the backend service and mount it at:
- `/var/data`

Set:
- `ALPHA_HIVE_DATA_DIR=/var/data/alpha_hive`

### 2) Render Postgres
Create a Postgres instance and set:
- `ALPHA_HIVE_DATABASE_URL=<internal database url>`

The project already supports Postgres and falls back to SQLite when unavailable, but on Render production you should prefer Postgres.

## Required secrets

### Backend secrets
- `TWELVE_API_KEY_1`
- `TWELVE_API_KEY_2` optional
- `FINNHUB_API_KEY` optional
- `ALPHA_VANTAGE_API_KEY` optional
- `BINANCE_FUTURES_API_KEY`
- `BINANCE_FUTURES_API_SECRET`

### Backend config
- `ALLOWED_ORIGINS=https://your-frontend.onrender.com`
- `BINANCE_FUTURES_TESTNET=1`
- `BINANCE_FUTURES_EXECUTION_MODE=paper`
- `BINANCE_FUTURES_AUTO_EXECUTION=0`
- `ALPHA_HIVE_LOG_LEVEL=INFO`

### Frontend config
- `NEXT_PUBLIC_API_BASE_URL=https://your-backend.onrender.com`

## First live checks

- open backend root URL and confirm service metadata returns JSON
- open `/api/v1/system/health`
- open frontend dashboard and confirm cards load
- test binary analyze endpoint
- test futures analyze endpoint before connecting keys
- connect Binance testnet only
- keep live auto execution disabled until logs and PnL tracking are verified
