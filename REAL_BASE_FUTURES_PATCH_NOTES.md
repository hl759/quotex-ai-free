# Futures integration patch on top of the current Python + Render base

This patch was built to preserve the current Binary Options engine and deploy model.

## Preserved
- `app.py` remains the main Flask entrypoint.
- `Procfile` remains `gunicorn ... app:app`.
- `render.yaml` remains Python-native on Render.
- Existing Binary Options routes, scanner loop, UI, learning, journal, and storage flow stay intact.

## Added
- `futures_module.py`
- `self_optimization_engine.py`
- `binance_runtime_vault.py`
- `binance_broker_service.py`
- `futures_bot_service.py`

## Modified
- `app.py`
- `scanner.py`

## New futures endpoints
- `GET /futures/status`
- `POST /futures/connect`
- `POST /futures/disconnect`
- `GET /futures/account`
- `GET /futures/positions`
- `GET /futures/orders`
- `GET /futures/analyze`
- `POST /futures/execute`
- `POST /futures/close-report`
- `POST /futures/bot/start`
- `POST /futures/bot/stop`
- `GET /futures/bot/status`

## UI
A new `🚀 Futures` tab was added inside the current inline dashboard, instead of splitting the project into another frontend.

## Safety defaults
- Binary remains manual signals only.
- Futures execution defaults to `paper`.
- Live sending still requires credentials and the existing safety flag `BINANCE_FUTURES_AUTO_EXECUTION=1`.
- Runtime credentials entered in the UI are memory-only.

## Render env vars to add
- `BINANCE_FUTURES_AUTO_EXECUTION=0`
- `BINANCE_FUTURES_EXECUTION_MODE=paper`
- `BINANCE_FUTURES_TESTNET=1`
- `BINANCE_FUTURES_MAX_LEVERAGE=8`
- optional persistent credentials:
  - `BINANCE_FUTURES_API_KEY`
  - `BINANCE_FUTURES_API_SECRET`

## Recommended first deployment
Use:
- testnet on
- paper mode on
- auto execution off

Only after validating the panel, analysis, account read, and paper bot flow should you switch to live.
