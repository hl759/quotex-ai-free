from config import DEFAULT_PAYOUT, EXECUTION_DELAY_CANDLES


class ResultEvaluator:
    def __init__(self):
        pass

    def evaluate(self, signal, candles):
        """
        Avalia o resultado olhando a vela de expiração e devolve
        resultado econômico básico (payout, stake, pnl e break-even).
        """
        try:
            if not candles or len(candles) < 2:
                return None

            execution_delay = self._safe_int(
                signal.get("execution_delay_candles", EXECUTION_DELAY_CANDLES),
                EXECUTION_DELAY_CANDLES,
            )
            exit_index = len(candles) - 1
            entry_index = max(0, exit_index - 1 - max(0, execution_delay))

            if entry_index >= exit_index:
                return None

            entry_candle = candles[entry_index]
            exit_candle = candles[exit_index]

            entry_price = self._extract_close(entry_candle)
            exit_price = self._extract_close(exit_candle)
            if entry_price is None or exit_price is None:
                return None

            side = str(signal.get("signal", "")).upper()
            if side == "CALL":
                if exit_price > entry_price:
                    result = "WIN"
                elif exit_price < entry_price:
                    result = "LOSS"
                else:
                    result = "DRAW"
            elif side == "PUT":
                if exit_price < entry_price:
                    result = "WIN"
                elif exit_price > entry_price:
                    result = "LOSS"
                else:
                    result = "DRAW"
            else:
                return None

            payout = max(0.0, self._safe_float(signal.get("payout"), DEFAULT_PAYOUT))
            stake = max(0.0, self._safe_float(
                signal.get("stake_value", signal.get("suggested_stake", signal.get("stake", 1.0))),
                1.0,
            ))

            if result == "WIN":
                gross_pnl = round(stake * payout, 2)
                gross_r = round(payout, 4)
            elif result == "LOSS":
                gross_pnl = round(-stake, 2)
                gross_r = -1.0
            else:
                gross_pnl = 0.0
                gross_r = 0.0

            breakeven_winrate = round((1.0 / (1.0 + payout)) * 100.0, 2) if payout > 0 else 100.0

            return {
                "uid": signal.get("uid"),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "entry_candle_time": self._extract_datetime(entry_candle),
                "exit_candle_time": self._extract_datetime(exit_candle),
                "result": result,
                "win": result == "WIN",
                "stake": stake,
                "payout": payout,
                "gross_pnl": gross_pnl,
                "gross_r": gross_r,
                "breakeven_winrate": breakeven_winrate,
                "evaluation_mode": "candle_close",
                "execution_delay_candles": int(max(0, execution_delay)),
            }
        except Exception:
            return None

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _safe_int(self, value, default=0):
        try:
            return int(float(value))
        except Exception:
            return int(default)

    def _extract_datetime(self, candle):
        if isinstance(candle, dict):
            for key in ("datetime", "time", "timestamp", "date"):
                if key in candle:
                    return str(candle.get(key))
            return None
        if isinstance(candle, (list, tuple)) and len(candle) >= 1:
            return str(candle[0])
        return None

    def _extract_close(self, candle):
        if isinstance(candle, dict):
            for key in ("close", "c", "Close"):
                if key in candle:
                    try:
                        return float(candle[key])
                    except Exception:
                        return None
            return None

        if isinstance(candle, (list, tuple)):
            if len(candle) >= 5:
                try:
                    return float(candle[4])
                except Exception:
                    return None
            return None

        return None
