class ResultEvaluator:
    def evaluate(self, signal, candles):
        try:
            if not candles or len(candles) < 2:
                return None

            entry_price = float(candles[-2]["close"])
            exit_price = float(candles[-1]["close"])
            signal_type = signal.get("signal", "CALL")

            result = "WIN" if (
                (signal_type == "CALL" and exit_price > entry_price) or
                (signal_type != "CALL" and exit_price < entry_price)
            ) else "LOSS"

            return {"entry_price": entry_price, "exit_price": exit_price, "result": result}
        except Exception:
            return None
