from datetime import datetime, timedelta, timezone
from config import BRAZIL_UTC_OFFSET_HOURS

BRAZIL_TZ = timezone(timedelta(hours=BRAZIL_UTC_OFFSET_HOURS))

class ResultEvaluator:
    def __init__(self, data_manager, learning_engine):
        self.data_manager = data_manager
        self.learning = learning_engine

    def process_pending(self):
        pending = self.learning.get_pending_signals()
        if not pending:
            return
        now_ts = int(datetime.now(BRAZIL_TZ).timestamp())
        for signal in pending[:]:
            if not signal.get("expiration_ts") or now_ts < signal["expiration_ts"]:
                continue
            result_record = self.evaluate_signal(signal)
            if result_record:
                self.learning.save_result(result_record)
            self.learning.remove_pending_signal(signal.get("signal_id"))

    def evaluate_signal(self, signal):
        candles = self.data_manager.get_candles(signal.get("asset"), interval="1min", outputsize=5)
        if not candles or len(candles) < 2:
            return None
        try:
            entry_price = float(candles[1]["close"])
            exit_price = float(candles[0]["close"])
        except Exception:
            return None
        direction = signal.get("signal", "CALL")
        result = "WIN"
        if direction == "CALL" and exit_price <= entry_price:
            result = "LOSS"
        if direction == "PUT" and exit_price >= entry_price:
            result = "LOSS"
        return {
            "signal_id": signal.get("signal_id"),
            "asset": signal.get("asset"),
            "signal": direction,
            "score": signal.get("score"),
            "confidence": signal.get("confidence"),
            "analysis_time": signal.get("analysis_time"),
            "entry_time": signal.get("entry_time"),
            "expiration": signal.get("expiration"),
            "provider": signal.get("provider"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "result": result,
            "generated_at": signal.get("generated_at"),
        }
