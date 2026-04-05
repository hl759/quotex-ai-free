# API Integration Guide

## Connect Binance credentials

`POST /api/v1/futures/connect`

```json
{
  "apiKey": "YOUR_API_KEY",
  "secretKey": "YOUR_SECRET_KEY",
  "testnet": true
}
```

## Analyze Binary Options

`GET /api/v1/binary/analyze`

Returns:

```json
{
  "ok": true,
  "data": {
    "mode": "BINARY_MODE",
    "asset": "BTCUSDT",
    "signal": "BUY",
    "expiration": "M1",
    "confidence": 78,
    "reason": ["..."]
  }
}
```

## Analyze Futures

`GET /api/v1/futures/analyze?asset=BTCUSDT&timeframe=1min&strategy=institutional_confluence`

Returns a ready-to-execute trade plan containing:

- direction
- entry
- stop_loss
- take_profits
- risk_reward
- leverage
- quantity
- confidence
- reason

## Execute Futures plan

`POST /api/v1/futures/execute`

```json
{
  "mode": "paper",
  "useTrailingStop": false,
  "trailingCallbackRate": 1.2,
  "plan": {
    "asset": "BTCUSDT",
    "status": "READY",
    "direction": "LONG",
    "quantity": 0.01,
    "entry": 65000,
    "stop_loss": 64500,
    "leverage": 5,
    "take_profits": [
      {"label": "TP1", "price": 65600, "size_pct": 40},
      {"label": "TP2", "price": 66000, "size_pct": 35}
    ]
  }
}
```

## Start automation bot

`POST /api/v1/futures/bot/start`

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1min",
  "strategy": "institutional_confluence",
  "executionMode": "paper",
  "maxTradesPerDay": 6,
  "pollSeconds": 20,
  "useTrailingStop": false,
  "trailingCallbackRate": 1.2
}
```

## Dashboard snapshot

`GET /api/v1/system/dashboard`

This is the preferred endpoint for the frontend because it aggregates:

- active mode
- latest binary signal
- latest futures plan
- connection status
- bot status
- account snapshot
- performance metrics
- equity curve data
