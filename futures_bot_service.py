
import threading
import time
from copy import deepcopy

from core.security import sanitize_error


class FuturesBotService:
    def __init__(self, analyze_fn, execute_fn, logger=None):
        self.analyze_fn = analyze_fn
        self.execute_fn = execute_fn
        self.logger = logger
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        self._last_plan_uid = ""
        self._config = {
            "symbol": "BTCUSDT",
            "timeframe": "1min",
            "strategy": "institutional_confluence",
            "execution_mode": "paper",
            "max_trades_per_day": 6,
            "poll_seconds": 20,
            "use_trailing_stop": False,
            "trailing_callback_rate": 1.2,
        }
        self._state = {
            "running": False,
            "started_at": None,
            "last_cycle_at": None,
            "last_error": "",
            "last_plan": None,
            "daily_trade_count": 0,
            "trade_day": time.strftime("%Y-%m-%d"),
        }

    def _log(self, message, level="info"):
        if not self.logger:
            return
        getattr(self.logger, level, self.logger.info)(message)

    def _roll_day(self):
        day = time.strftime("%Y-%m-%d")
        if self._state.get("trade_day") != day:
            self._state["trade_day"] = day
            self._state["daily_trade_count"] = 0

    def status(self):
        with self._lock:
            return {
                **deepcopy(self._state),
                "config": deepcopy(self._config),
            }

    def start(self, config=None):
        with self._lock:
            if isinstance(config, dict):
                self._config.update({k: v for k, v in config.items() if v is not None and v != ""})
            if self._state.get("running"):
                return self.status()
            self._stop_event.clear()
            self._state.update({
                "running": True,
                "started_at": int(time.time()),
                "last_error": "",
            })
            self._thread = threading.Thread(target=self._run_loop, name="futures-bot-service", daemon=True)
            self._thread.start()
        self._log("futures bot started")
        return self.status()

    def stop(self):
        with self._lock:
            self._state["running"] = False
            self._stop_event.set()
        self._log("futures bot stopped")
        return self.status()

    def _run_loop(self):
        while not self._stop_event.is_set():
            self._roll_day()
            try:
                if int(self._state.get("daily_trade_count", 0)) >= int(float(self._config.get("max_trades_per_day", 6) or 6)):
                    self._state["last_error"] = "daily_trade_limit_reached"
                else:
                    plan = self.analyze_fn(
                        asset=self._config.get("symbol"),
                        timeframe=self._config.get("timeframe", "1min"),
                        strategy_name=self._config.get("strategy", "institutional_confluence"),
                        execution_mode="paper",
                    )
                    self._state["last_plan"] = deepcopy(plan)
                    if isinstance(plan, dict) and str(plan.get("status")).upper() == "READY":
                        uid = str(plan.get("uid") or "")
                        if uid and uid != self._last_plan_uid:
                            result = self.execute_fn(
                                plan,
                                mode=self._config.get("execution_mode", "paper"),
                                use_trailing_stop=bool(self._config.get("use_trailing_stop", False)),
                                trailing_callback_rate=float(self._config.get("trailing_callback_rate", 1.2) or 1.2),
                            )
                            self._last_plan_uid = uid
                            if result.get("ok"):
                                self._state["daily_trade_count"] = int(self._state.get("daily_trade_count", 0)) + 1
            except Exception as exc:
                self._state["last_error"] = sanitize_error(exc)
                self._log(f"futures bot cycle failed: {sanitize_error(exc)}", level="error")
            self._state["last_cycle_at"] = int(time.time())
            wait_seconds = max(5, int(float(self._config.get("poll_seconds", 20) or 20)))
            self._stop_event.wait(wait_seconds)
