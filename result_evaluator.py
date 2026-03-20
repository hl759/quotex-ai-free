class ResultEvaluator:
    def __init__(self):
        pass

    def evaluate(self, signal, candles):
        """
        Avalia o resultado olhando a vela de expiração.
        Compatível com diferentes formatos de candle:
        - dict com close/open
        - lista/tupla [timestamp, open, high, low, close]
        """
        try:
            if not candles or len(candles) < 2:
                return None

            entry_price = self._extract_close(candles[-2])
            exit_price = self._extract_close(candles[-1])

            if entry_price is None or exit_price is None:
                return None

            side = str(signal.get("signal", "")).upper()

            if side == "CALL":
                result = "WIN" if exit_price > entry_price else "LOSS"
            elif side == "PUT":
                result = "WIN" if exit_price < entry_price else "LOSS"
            else:
                return None

            return {
                "entry_price": entry_price,
                "exit_price": exit_price,
                "result": result,
                "win": result == "WIN"
            }
        except Exception:
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
