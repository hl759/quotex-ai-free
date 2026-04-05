# Hybrid Usage

## Binary mode

- Legacy UI and legacy routes remain unchanged.
- New standardized API:
  - `GET /binary/analyze`

## Futures mode

- Analyze best futures setup:
  - `GET /futures/analyze`
- Analyze a specific symbol:
  - `GET /futures/analyze?asset=BTCUSDT`
- Generate execution payload:
  - `POST /futures/execute`
- Register closed trade outcome for the optimizer:
  - `POST /futures/close-report`

## Mode selection

- Read active mode:
  - `GET /mode`
- Change mode:
  - `POST /mode` with `{ "mode": "BINARY_MODE" }` or `{ "mode": "FUTURES_MODE" }`

## Hybrid scan

- Run a mode-aware scan:
  - `GET /hybrid/run-scan?mode=BINARY_MODE`
  - `GET /hybrid/run-scan?mode=FUTURES_MODE&asset=BTCUSDT&execution_mode=paper`
- Read hybrid snapshot:
  - `GET /hybrid/snapshot`

## Live execution safeguards

Live futures execution is disabled by default.
To allow live order sending, set:

- `BINANCE_FUTURES_AUTO_EXECUTION=1`
- `BINANCE_FUTURES_API_KEY=...`
- `BINANCE_FUTURES_API_SECRET=...`

Without these settings, the futures executor stays in paper/payload mode.
