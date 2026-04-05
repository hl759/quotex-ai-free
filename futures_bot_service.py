import json
import os
import threading
import time
from datetime import datetime

from json_safe import safe_dump
from storage_paths import STATE_DIR


class FuturesBotService:
    def __init__(self, scanner, futures_module, capital_state_loader):
        self.scanner = scanner
        self.futures_module = futures_module
        self.capital_state_loader = capital_state_loader
        self._lock = threading.RLock()
        self._thread = None
        self._stop_flag = threading.Event()
        self.state_path = os.path.join(STATE_DIR, "futures_bot_state.json")
        self.state = self._load_state()

    def _default_state(self):
        return {
            "running": False,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "execution_mode": "paper",
            "strategy": "futures_confluence",
            "risk_per_trade_pct": 0.6,
            "leverage": 3,
            "max_trades_per_day": 3,
            "poll_seconds": 45,
            "last_plan_uid": None,
            "last_run_at": None,
            "last_error": None,
            "last_result": None,
            "trade_day": None,
            "trades_today": 0,
            "logs": [],
        }

    def _load_state(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    base = self._default_state()
                    base.update(data)
                    return base
            except Exception:
                pass
        return self._default_state()

    def _save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(self.state, f)
        os.replace(tmp, self.state_path)

    def _log(self, message, level="info"):
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": str(message),
        }
        self.state.setdefault("logs", []).append(entry)
        self.state["logs"] = self.state["logs"][-80:]
        self._save()

    def _roll_day(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self.state.get("trade_day") != today:
            self.state["trade_day"] = today
            self.state["trades_today"] = 0

    def start(self, config=None):
        with self._lock:
            cfg = dict(config or {})
            for k in ("symbol", "timeframe", "execution_mode", "strategy"):
                if k in cfg and cfg[k] not in (None, ""):
                    self.state[k] = cfg[k]
            for k in ("risk_per_trade_pct", "leverage", "max_trades_per_day", "poll_seconds"):
                if k in cfg and cfg[k] not in (None, ""):
                    self.state[k] = cfg[k]
            self.state["running"] = True
            self._stop_flag.clear()
            self._roll_day()
            self._save()
            self._log(f"Bot iniciado em {self.state.get('execution_mode')} para {self.state.get('symbol')}")
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
            return self.status()

    def stop(self):
        with self._lock:
            self.state["running"] = False
            self._stop_flag.set()
            self._save()
            self._log("Bot parado pelo usuário", level="warn")
            return self.status()

    def status(self):
        with self._lock:
            snap = dict(self.state)
            snap["thread_alive"] = bool(self._thread and self._thread.is_alive())
            return snap

    def _loop(self):
        while not self._stop_flag.is_set():
            try:
                with self._lock:
                    self._roll_day()
                    running = bool(self.state.get("running"))
                    symbol = str(self.state.get("symbol") or "BTCUSDT").upper().strip()
                    timeframe = str(self.state.get("timeframe") or "1m").strip()
                    execution_mode = str(self.state.get("execution_mode") or "paper").strip().lower()
                    poll_seconds = max(20, int(float(self.state.get("poll_seconds") or 45)))
                    leverage = int(float(self.state.get("leverage") or 3))
                    risk_per_trade_pct = float(self.state.get("risk_per_trade_pct") or 0.6)
                    max_trades_per_day = max(1, int(float(self.state.get("max_trades_per_day") or 3)))
                if not running:
                    time.sleep(1.0)
                    continue

                if int(self.state.get("trades_today") or 0) >= max_trades_per_day:
                    self.state["last_result"] = {
                        "plan": None,
                        "execution": {"note": f"Limite diário atingido: {max_trades_per_day} trades."},
                    }
                    self._save()
                    self._log(f"Limite diário atingido para {symbol}", level="warn")
                    time.sleep(poll_seconds)
                    continue

                market = self.scanner.scan_assets(timeframe=timeframe, assets=[symbol], outputsize=120)
                plan = self.futures_module.analyze_market(
                    market,
                    capital_state=self.capital_state_loader(),
                    asset=symbol,
                    execution_mode=execution_mode,
                    timeframe=timeframe,
                    strategy_name=str(self.state.get("strategy") or "futures_confluence"),
                    leverage_override=leverage,
                    risk_pct_override=(risk_per_trade_pct / 100.0),
                    max_trades_per_day=max_trades_per_day,
                )
                execution = None
                if plan.get("status") == "READY" and plan.get("uid") != self.state.get("last_plan_uid"):
                    execution = self.futures_module.execute_signal(plan, live=(execution_mode == "live"))
                    self.state["last_plan_uid"] = plan.get("uid")
                    if execution.get("executed") or execution.get("execution_mode") == "paper":
                        self.state["trades_today"] = int(self.state.get("trades_today") or 0) + 1
                    self._log(f"Plano {plan.get('uid')} processado em {execution_mode}: {execution.get('note')}")
                else:
                    self._log(f"Sem nova execução para {symbol}: {plan.get('status')}", level="debug")

                self.state["last_run_at"] = datetime.utcnow().isoformat() + "Z"
                self.state["last_result"] = {
                    "plan": plan,
                    "execution": execution,
                }
                self.state["last_error"] = None
                self._save()
                time.sleep(poll_seconds)
            except Exception as exc:
                self.state["last_error"] = str(exc)
                self._save()
                self._log(f"Erro no loop futures: {exc}", level="error")
                time.sleep(6)
