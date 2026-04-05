import hashlib
import hmac
import math
import os
import time
from copy import deepcopy
from urllib.parse import urlencode

import pandas as pd
import requests


class FuturesModule:
    """
    Módulo novo para Binance Futures.
    Foco: estrutura pronta para automação, com live desligado por padrão.
    """

    def __init__(self, data_manager, self_optimizer=None):
        self.data_manager = data_manager
        self.self_optimizer = self_optimizer
        self.default_execution_mode = os.getenv("BINANCE_FUTURES_EXECUTION_MODE", "paper").strip().lower() or "paper"
        self.live_enabled = os.getenv("BINANCE_FUTURES_AUTO_EXECUTION", "0").strip().lower() in ("1", "true", "yes")
        self.base_url = os.getenv("BINANCE_FUTURES_BASE_URL", "https://fapi.binance.com").strip()
        self.api_key = os.getenv("BINANCE_FUTURES_API_KEY", "").strip()
        self.api_secret = os.getenv("BINANCE_FUTURES_API_SECRET", "").strip()
        self.max_leverage = max(2, int(float(os.getenv("BINANCE_FUTURES_MAX_LEVERAGE", "8") or 8)))

    def _safe_float(self, value, default=0.0):
        try:
            if value is None or value == "":
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def _ema(self, series, span):
        return series.ewm(span=span, adjust=False).mean()

    def _rsi(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, 1e-9)
        return 100 - (100 / (1 + rs))

    def _atr(self, df, period=14):
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _macd(self, series, fast=12, slow=26, signal=9):
        fast_ema = self._ema(series, fast)
        slow_ema = self._ema(series, slow)
        macd_line = fast_ema - slow_ema
        signal_line = self._ema(macd_line, signal)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    def _to_df(self, candles):
        df = pd.DataFrame(candles)
        if df.empty:
            return df
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        return df

    def _aggregate_to_m5(self, df):
        if df is None or df.empty or len(df) < 15:
            return None
        tmp = df.copy()
        tmp["grp"] = list(range(len(tmp)))[::-1]
        tmp["grp"] = tmp["grp"] // 5
        agg = tmp.groupby("grp", sort=False).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        agg = agg.iloc[::-1].reset_index(drop=True)
        return agg

    def _market_structure(self, df):
        if df is None or len(df) < 25:
            return {"bias": "neutral", "swing_high": None, "swing_low": None, "structure_score": 0.0}
        recent = df.tail(20)
        prev = df.tail(40).head(20)
        recent_high = recent["high"].max()
        recent_low = recent["low"].min()
        prev_high = prev["high"].max()
        prev_low = prev["low"].min()
        bias = "neutral"
        score = 0.0
        if recent_high > prev_high and recent_low > prev_low:
            bias = "bullish"
            score = 1.2
        elif recent_high < prev_high and recent_low < prev_low:
            bias = "bearish"
            score = 1.2
        elif recent_high > prev_high and recent_low <= prev_low:
            bias = "expansion"
            score = 0.45
        return {
            "bias": bias,
            "swing_high": float(recent_high),
            "swing_low": float(recent_low),
            "structure_score": round(score, 4),
        }

    def _liquidity_read(self, df):
        if df is None or len(df) < 15:
            return {"type": "none", "score_long": 0.0, "score_short": 0.0}
        recent = df.tail(8)
        prev = df.tail(20).head(12)
        last = recent.iloc[-1]
        prev_high = float(prev["high"].max())
        prev_low = float(prev["low"].min())
        score_long = 0.0
        score_short = 0.0
        liq_type = "none"
        if float(last["low"]) < prev_low and float(last["close"]) > prev_low:
            score_long += 0.85
            liq_type = "sell_side_sweep"
        if float(last["high"]) > prev_high and float(last["close"]) < prev_high:
            score_short += 0.85
            liq_type = "buy_side_sweep"
        if float(last["close"]) > prev_high:
            score_long += 0.55
            liq_type = "breakout_acceptance_high"
        if float(last["close"]) < prev_low:
            score_short += 0.55
            liq_type = "breakout_acceptance_low"
        return {"type": liq_type, "score_long": round(score_long, 4), "score_short": round(score_short, 4)}

    def _price_action(self, df):
        if df is None or len(df) < 3:
            return {"bullish": False, "bearish": False, "impulse_long": 0.0, "impulse_short": 0.0}
        last = df.iloc[-1]
        prev = df.iloc[-2]
        bullish = float(last["close"]) > float(last["open"]) and float(prev["close"]) < float(prev["open"]) and float(last["close"]) >= float(prev["open"])
        bearish = float(last["close"]) < float(last["open"]) and float(prev["close"]) > float(prev["open"]) and float(last["close"]) <= float(prev["open"])
        candle_range = max(1e-9, float(last["high"]) - float(last["low"]))
        close_position = (float(last["close"]) - float(last["low"])) / candle_range
        impulse_long = 0.4 if close_position >= 0.72 else 0.0
        impulse_short = 0.4 if close_position <= 0.28 else 0.0
        if bullish:
            impulse_long += 0.55
        if bearish:
            impulse_short += 0.55
        return {
            "bullish": bullish,
            "bearish": bearish,
            "impulse_long": round(impulse_long, 4),
            "impulse_short": round(impulse_short, 4),
        }

    def _feature_pack(self, candles):
        df = self._to_df(candles)
        if df is None or df.empty or len(df) < 55:
            return None
        df["ema20"] = self._ema(df["close"], 20)
        df["ema50"] = self._ema(df["close"], 50)
        df["ema200"] = self._ema(df["close"], 200)
        df["rsi"] = self._rsi(df["close"], 14)
        macd_line, signal_line, hist = self._macd(df["close"])
        df["macd"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"] = hist
        df["atr"] = self._atr(df, 14)
        df["volume_sma"] = df["volume"].rolling(20).mean()

        last = df.iloc[-1]
        m5 = self._aggregate_to_m5(df)
        m5_trend = "neutral"
        if m5 is not None and len(m5) >= 20:
            m5["ema20"] = self._ema(m5["close"], 20)
            m5["ema50"] = self._ema(m5["close"], 50)
            if float(m5["ema20"].iloc[-1]) > float(m5["ema50"].iloc[-1]):
                m5_trend = "bullish"
            elif float(m5["ema20"].iloc[-1]) < float(m5["ema50"].iloc[-1]):
                m5_trend = "bearish"

        trend_m1 = "neutral"
        if float(last["ema20"]) > float(last["ema50"]):
            trend_m1 = "bullish"
        elif float(last["ema20"]) < float(last["ema50"]):
            trend_m1 = "bearish"

        structure = self._market_structure(df)
        liquidity = self._liquidity_read(df)
        price_action = self._price_action(df)
        volume_ratio = float(last["volume"]) / max(1e-9, float(last["volume_sma"]) or 1e-9)
        volatility_pct = float(last["atr"]) / max(1e-9, float(last["close"]))

        return {
            "df": df,
            "last_price": float(last["close"]),
            "ema20": float(last["ema20"]),
            "ema50": float(last["ema50"]),
            "ema200": float(last["ema200"]),
            "rsi": float(last["rsi"] if not math.isnan(float(last["rsi"])) else 50.0),
            "macd_hist": float(last["macd_hist"]),
            "macd_line": float(last["macd"]),
            "macd_signal": float(last["macd_signal"]),
            "atr": float(last["atr"] if not math.isnan(float(last["atr"])) else 0.0),
            "volume_ratio": volume_ratio,
            "volatility_pct": volatility_pct,
            "trend_m1": trend_m1,
            "trend_m5": m5_trend,
            "structure": structure,
            "liquidity": liquidity,
            "price_action": price_action,
        }

    def _score_direction(self, features, direction):
        direction = str(direction).upper()
        is_long = direction == "LONG"
        score = 0.0
        reasons = []

        if is_long and features["trend_m1"] == "bullish":
            score += 1.15
            reasons.append("EMA20 > EMA50 no M1")
        if (not is_long) and features["trend_m1"] == "bearish":
            score += 1.15
            reasons.append("EMA20 < EMA50 no M1")

        if is_long and features["trend_m5"] == "bullish":
            score += 1.05
            reasons.append("M5 alinhado na compra")
        if (not is_long) and features["trend_m5"] == "bearish":
            score += 1.05
            reasons.append("M5 alinhado na venda")

        rsi = features["rsi"]
        if is_long and 48 <= rsi <= 69:
            score += 0.72
            reasons.append("RSI saudável para LONG")
        elif (not is_long) and 31 <= rsi <= 52:
            score += 0.72
            reasons.append("RSI saudável para SHORT")
        elif is_long and rsi < 35:
            score += 0.30
            reasons.append("RSI descontado pode sustentar reversão de alta")
        elif (not is_long) and rsi > 65:
            score += 0.30
            reasons.append("RSI esticado pode sustentar reversão de baixa")

        if is_long and features["macd_hist"] > 0 and features["macd_line"] >= features["macd_signal"]:
            score += 0.75
            reasons.append("MACD confirma momentum comprador")
        if (not is_long) and features["macd_hist"] < 0 and features["macd_line"] <= features["macd_signal"]:
            score += 0.75
            reasons.append("MACD confirma momentum vendedor")

        if features["volume_ratio"] >= 1.08:
            score += 0.55
            reasons.append("Volume acima da média")
        elif features["volume_ratio"] <= 0.85:
            score -= 0.22
            reasons.append("Volume abaixo do ideal")

        structure_bias = features["structure"].get("bias")
        if is_long and structure_bias == "bullish":
            score += 0.95
            reasons.append("Estrutura HH/HL")
        elif (not is_long) and structure_bias == "bearish":
            score += 0.95
            reasons.append("Estrutura LL/LH")
        elif structure_bias == "expansion":
            score += 0.20
            reasons.append("Estrutura expansiva")

        liquidity = features["liquidity"]
        if is_long and liquidity.get("score_long", 0.0) > 0:
            score += liquidity.get("score_long", 0.0)
            reasons.append(f"Liquidez favorável: {liquidity.get('type', 'none')}")
        elif (not is_long) and liquidity.get("score_short", 0.0) > 0:
            score += liquidity.get("score_short", 0.0)
            reasons.append(f"Liquidez favorável: {liquidity.get('type', 'none')}")

        price_action = features["price_action"]
        impulse = price_action.get("impulse_long" if is_long else "impulse_short", 0.0)
        if impulse > 0:
            score += impulse
            reasons.append("Price action confirma gatilho")

        if features["volatility_pct"] >= 0.012:
            score -= 0.45
            reasons.append("Volatilidade alta reduziu agressividade")
        elif features["volatility_pct"] <= 0.002:
            score -= 0.18
            reasons.append("Volatilidade comprimida demais")

        return round(max(0.0, score), 4), reasons

    def _compute_confidence(self, score, adjustment):
        confidence = 50 + (score * 7.0)
        confidence *= (2.0 - float(adjustment.get("score_multiplier", 1.0) or 1.0))
        return int(max(50, min(95, round(confidence))))

    def _trade_levels(self, direction, features):
        price = features["last_price"]
        atr = max(1e-9, features["atr"])
        swing_high = features["structure"].get("swing_high") or price + atr
        swing_low = features["structure"].get("swing_low") or price - atr
        if str(direction).upper() == "LONG":
            entry = price
            stop = min(swing_low, price - (1.25 * atr))
            risk = max(1e-9, entry - stop)
            tp1 = entry + risk * 1.20
            tp2 = entry + risk * 1.90
            tp3 = entry + risk * 2.75
        else:
            entry = price
            stop = max(swing_high, price + (1.25 * atr))
            risk = max(1e-9, stop - entry)
            tp1 = entry - risk * 1.20
            tp2 = entry - risk * 1.90
            tp3 = entry - risk * 2.75
        return {
            "entry": round(entry, 6),
            "stop_loss": round(stop, 6),
            "risk_per_unit": round(risk, 6),
            "take_profits": [
                {"label": "TP1", "price": round(tp1, 6), "rr": 1.2, "size_pct": 40},
                {"label": "TP2", "price": round(tp2, 6), "rr": 1.9, "size_pct": 35},
                {"label": "TP3", "price": round(tp3, 6), "rr": 2.75, "size_pct": 25},
            ],
            "risk_reward": 1.9,
        }

    def _position_plan(self, entry, risk_per_unit, leverage, capital_state, risk_profile):
        capital_current = max(0.0, self._safe_float((capital_state or {}).get("capital_current"), 0.0))
        if capital_current <= 0:
            capital_current = 100.0
        risk_pct = float(risk_profile.get("risk_pct", 0.005) or 0.005)
        risk_amount = capital_current * risk_pct
        quantity = risk_amount / max(1e-9, risk_per_unit)
        notional = quantity * entry
        margin_estimate = notional / max(1.0, leverage)
        return {
            "capital_reference": round(capital_current, 4),
            "risk_pct": round(risk_pct, 4),
            "risk_amount": round(risk_amount, 4),
            "quantity": round(quantity, 6),
            "notional_estimate": round(notional, 4),
            "margin_estimate": round(margin_estimate, 4),
        }

    def _leverage(self, confidence, features, adjustment):
        if confidence >= 84:
            leverage = 7
        elif confidence >= 75:
            leverage = 5
        else:
            leverage = 3
        if features["volatility_pct"] >= 0.010:
            leverage -= 1
        leverage = leverage * float(adjustment.get("leverage_multiplier", 1.0) or 1.0)
        leverage = int(max(2, min(self.max_leverage, round(leverage))))
        return leverage

    def _build_payload(self, plan):
        side = "BUY" if str(plan.get("direction")) == "LONG" else "SELL"
        exit_side = "SELL" if side == "BUY" else "BUY"
        entry = plan.get("entry")
        stop = plan.get("stop_loss")
        qty = plan.get("quantity")
        take_profits = plan.get("take_profits", [])
        return {
            "exchange": "BINANCE_FUTURES",
            "symbol": plan.get("asset"),
            "entry_order": {
                "type": "MARKET",
                "side": side,
                "quantity": qty,
                "reduceOnly": False,
            },
            "protective_stop": {
                "type": "STOP_MARKET",
                "side": exit_side,
                "stopPrice": stop,
                "closePosition": False,
                "quantity": qty,
                "reduceOnly": True,
            },
            "take_profit_orders": [
                {
                    "label": tp.get("label"),
                    "type": "TAKE_PROFIT_MARKET",
                    "side": exit_side,
                    "stopPrice": tp.get("price"),
                    "quantity": round(qty * (float(tp.get("size_pct", 0.0)) / 100.0), 6),
                    "reduceOnly": True,
                }
                for tp in take_profits
            ],
            "leverage": plan.get("leverage"),
            "entry_reference": entry,
        }

    def _sign(self, params):
        query = urlencode(params, doseq=True)
        signature = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    def execute_signal(self, plan, live=False):
        payload = self._build_payload(plan)
        if not live:
            return {
                "execution_mode": "paper",
                "executed": False,
                "can_execute": True,
                "payload": payload,
                "note": "Paper mode: payload gerado, nenhuma ordem enviada.",
            }

        if not self.live_enabled:
            return {
                "execution_mode": "live",
                "executed": False,
                "can_execute": False,
                "payload": payload,
                "note": "Live desabilitado por configuração.",
            }

        if not self.api_key or not self.api_secret:
            return {
                "execution_mode": "live",
                "executed": False,
                "can_execute": False,
                "payload": payload,
                "note": "Credenciais Binance Futures ausentes.",
            }

        headers = {"X-MBX-APIKEY": self.api_key}
        responses = []
        try:
            leverage_params = {
                "symbol": plan.get("asset"),
                "leverage": int(plan.get("leverage") or 2),
                "timestamp": int(time.time() * 1000),
            }
            leverage_query = self._sign(leverage_params)
            responses.append(requests.post(f"{self.base_url}/fapi/v1/leverage?{leverage_query}", headers=headers, timeout=8).json())

            for order in [payload["entry_order"], payload["protective_stop"], *payload.get("take_profit_orders", [])]:
                params = {
                    "symbol": plan.get("asset"),
                    "side": order.get("side"),
                    "type": order.get("type"),
                    "quantity": order.get("quantity"),
                    "timestamp": int(time.time() * 1000),
                }
                if order.get("type") in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
                    params["stopPrice"] = order.get("stopPrice")
                    params["reduceOnly"] = "true"
                    params["workingType"] = "MARK_PRICE"
                query = self._sign(params)
                responses.append(requests.post(f"{self.base_url}/fapi/v1/order?{query}", headers=headers, timeout=8).json())

            return {
                "execution_mode": "live",
                "executed": True,
                "can_execute": True,
                "payload": payload,
                "exchange_responses": responses,
                "note": "Ordem e proteções enviadas para a Binance Futures.",
            }
        except Exception as e:
            return {
                "execution_mode": "live",
                "executed": False,
                "can_execute": False,
                "payload": payload,
                "note": f"Falha no envio live: {e}",
            }

    def analyze_market(self, market, capital_state=None, asset=None, execution_mode=None):
        execution_mode = str(execution_mode or self.default_execution_mode or "paper").lower()
        candidates = []
        for item in market or []:
            symbol = str(item.get("asset") or "").upper()
            if asset and symbol != str(asset).upper().strip():
                continue
            if not symbol.endswith(("USDT", "BUSD")):
                continue
            candles = item.get("candles")
            if not candles:
                candles = self.data_manager.get_candles(symbol, interval="1min", outputsize=120)
            if not candles:
                continue
            features = self._feature_pack(candles)
            if not features:
                continue
            long_score, long_reasons = self._score_direction(features, "LONG")
            short_score, short_reasons = self._score_direction(features, "SHORT")
            if long_score >= short_score:
                direction = "LONG"
                score = long_score
                reasons = long_reasons
            else:
                direction = "SHORT"
                score = short_score
                reasons = short_reasons
            candidates.append({
                "asset": symbol,
                "features": features,
                "direction": direction,
                "score": score,
                "reasons": reasons,
                "provider": item.get("provider", "auto"),
            })

        if not candidates:
            return {
                "mode": "FUTURES_MODE",
                "status": "NO_TRADE",
                "asset": str(asset or "MERCADO"),
                "direction": None,
                "confidence": 50,
                "reason": ["Nenhum ativo futures elegível com dados suficientes"],
            }

        candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        best = candidates[0]
        symbol = best["asset"]
        features = best["features"]
        market_condition = f"{features['trend_m1']}|{features['trend_m5']}|{features['structure'].get('bias','neutral')}"
        analysis_time = time.strftime("%H:%M")

        adjustment = self.self_optimizer.get_mode_adjustments(
            mode="FUTURES_MODE",
            asset=symbol,
            setup_type="futures_confluence",
            market_condition=market_condition,
            analysis_time=analysis_time,
            capital_state=capital_state,
        ) if self.self_optimizer else {
            "confidence_floor": 62,
            "score_multiplier": 1.0,
            "risk_multiplier": 1.0,
            "leverage_multiplier": 1.0,
            "allow_trade": True,
            "frequency_limit": 1,
            "reasons": [],
        }

        score = round(float(best["score"]) / max(1e-9, float(adjustment.get("score_multiplier", 1.0) or 1.0)), 4)
        confidence = self._compute_confidence(score, adjustment)
        levels = self._trade_levels(best["direction"], features)
        leverage = self._leverage(confidence, features, adjustment)
        risk_profile = self.self_optimizer.risk_profile("FUTURES_MODE", capital_state=capital_state) if self.self_optimizer else {"risk_pct": 0.0065, "allow_trade": True, "reasons": []}
        position = self._position_plan(levels["entry"], levels["risk_per_unit"], leverage, capital_state, risk_profile)

        status = "READY"
        reasons = list(best["reasons"])
        reasons.extend(adjustment.get("reasons", []))
        reasons.extend(risk_profile.get("reasons", []))

        if score < 4.45:
            status = "NO_TRADE"
            reasons.append("Confluência insuficiente para entrada futures")
        if confidence < adjustment.get("confidence_floor", 62):
            status = "NO_TRADE"
            reasons.append("Confiança abaixo do piso adaptativo")
        if not adjustment.get("allow_trade", True) or not risk_profile.get("allow_trade", True):
            status = "NO_TRADE"
            reasons.append("Gestão adaptativa bloqueou nova posição")

        plan = {
            "uid": f"FUT|{symbol}|{analysis_time}|{best['direction']}",
            "mode": "FUTURES_MODE",
            "status": status,
            "asset": symbol,
            "direction": best["direction"],
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "take_profits": levels["take_profits"],
            "risk_reward": levels["risk_reward"],
            "leverage": leverage,
            "confidence": confidence,
            "reason": reasons[:8],
            "provider": best.get("provider", "auto"),
            "setup_type": "futures_confluence",
            "market_condition": market_condition,
            "confluence_score": score,
            "analysis_time": analysis_time,
            "date": time.strftime("%Y-%m-%d"),
            "time_bucket": f"{analysis_time[:2]}:00" if ":" in analysis_time else "unknown",
            "quantity": position["quantity"],
            "risk_pct": position["risk_pct"],
            "risk_amount": position["risk_amount"],
            "notional_estimate": position["notional_estimate"],
            "margin_estimate": position["margin_estimate"],
            "capital_reference": position["capital_reference"],
            "trailing_stop": {
                "activation": "after_TP1",
                "method": "ATR",
                "atr_multiple": 1.0,
                "move_to_break_even_after_rr": 1.1,
            },
            "partial_take_profit_plan": levels["take_profits"],
            "volatility_pct": round(features["volatility_pct"], 6),
            "rsi": round(features["rsi"], 4),
            "ema20": round(features["ema20"], 6),
            "ema50": round(features["ema50"], 6),
            "ema200": round(features["ema200"], 6),
            "liquidity_context": features["liquidity"],
            "market_structure": features["structure"],
            "adjustment": adjustment,
            "risk_profile": risk_profile,
        }
        plan["automation_ready"] = self.execute_signal(plan, live=(execution_mode == "live" and status == "READY"))
        if self.self_optimizer and status == "READY":
            self.self_optimizer.register_futures_plan(plan)
        return plan
