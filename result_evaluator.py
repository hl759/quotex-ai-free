class ResultEvaluator:
    def evaluate(self, signal, candles):
        try:
            if not candles or len(candles)<2: return None
            entry_price=float(candles[-2]["close"]); exit_price=float(candles[-1]["close"])
            s=signal.get("signal","CALL")
            result="WIN" if ((s=="CALL" and exit_price>entry_price) or (s!="CALL" and exit_price<entry_price)) else "LOSS"
            return {"entry_price":entry_price,"exit_price":exit_price,"result":result}
        except Exception: return None
