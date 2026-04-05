
import os
import time
from copy import deepcopy

from binary_options_module import BinaryOptionsModule
from config import CRYPTO_ASSETS
from data_manager import DataManager
from decision_engine import DecisionEngine
from hybrid_mode_router import HybridModeRouter
from indicators import IndicatorEngine
from learning_engine import LearningEngine
from scanner import MarketScanner
from self_optimization_engine import SelfOptimizationEngine
from signal_engine import SignalEngine
from state_store import get_state_store
from futures_module import FuturesModule

from core.logging_config import configure_logging
from services.binance_futures_client import BinanceFuturesClient
from services.credential_vault import InMemoryCredentialVault
from services.execution_service import FuturesExecutionService
from services.futures_bot_service import FuturesBotService


class TradingPlatformRuntime:
    def __init__(self):
        self.logger = configure_logging()
        self.store = get_state_store()
        self.indicators = IndicatorEngine()
        self.learning = LearningEngine()
        self.data_manager = DataManager()
        self.scanner = MarketScanner(self.data_manager, self.learning)
        self.signal_engine = SignalEngine(self.learning)
        self.decision_engine = DecisionEngine(self.learning)
        self.self_optimizer = SelfOptimizationEngine()
        self.binary_module = BinaryOptionsModule(self.decision_engine, self.signal_engine, self_optimizer=self.self_optimizer)
        self.futures_module = FuturesModule(self.data_manager, self_optimizer=self.self_optimizer)
        self.hybrid_router = HybridModeRouter(
            binary_module=self.binary_module,
            futures_module=self.futures_module,
            self_optimizer=self.self_optimizer,
            scanner=self.scanner,
            capital_state_loader=self.load_capital_state,
        )
        self.vault = InMemoryCredentialVault()
        self.binance_client = BinanceFuturesClient(self.vault, logger=self.logger)
        self.execution_service = FuturesExecutionService(self.binance_client, self_optimizer=self.self_optimizer, logger=self.logger)
        self.bot_service = FuturesBotService(
            analyze_fn=self.analyze_futures,
            execute_fn=self.execution_service.execute_plan,
            logger=self.logger,
        )
        self.latest_binary = None
        self.latest_futures = None
        self.latest_execution = None
        self.logger.info("TradingPlatformRuntime initialized")

    def load_capital_state(self):
        state = self.store.get_json("capital_state", None)
        if not isinstance(state, dict):
            state = {
                "capital_current": float(os.getenv("TRADING_CAPITAL_CURRENT", "1000") or 1000),
                "capital_peak": float(os.getenv("TRADING_CAPITAL_PEAK", "1000") or 1000),
                "daily_pnl": 0.0,
                "streak": 0,
                "daily_target_pct": 2.0,
                "daily_stop_pct": 3.0,
            }
        state.setdefault("capital_current", 1000.0)
        state.setdefault("capital_peak", state.get("capital_current", 1000.0))
        state.setdefault("daily_pnl", 0.0)
        state.setdefault("streak", 0)
        state.setdefault("daily_target_pct", 2.0)
        state.setdefault("daily_stop_pct", 3.0)
        return state

    def save_capital_state(self, payload):
        current = self.load_capital_state()
        merged = {**current, **(payload or {})}
        self.store.set_json("capital_state", merged)
        return merged

    def connection_status(self):
        status = self.vault.status()
        status["ping"] = self.binance_client.ping()
        return status

    def connect_binance(self, api_key, api_secret, testnet=False):
        status = self.vault.connect(api_key=api_key, api_secret=api_secret, testnet=testnet)
        status["ping"] = self.binance_client.ping()
        return status

    def disconnect_binance(self):
        return self.vault.disconnect()

    def set_mode(self, mode):
        return self.hybrid_router.set_active_mode(mode)

    def get_mode(self):
        return self.hybrid_router.get_active_mode()

    def analyze_binary(self):
        market = self.scanner.scan_assets(interval="1min", outputsize=50)
        result = self.binary_module.analyze_market(market, capital_state=self.load_capital_state())
        self.latest_binary = deepcopy(result)
        return result

    def analyze_futures(self, asset=None, timeframe="1min", strategy_name="institutional_confluence", execution_mode="paper"):
        asset = str(asset or "").upper().strip() or None
        assets = [asset] if asset else list(CRYPTO_ASSETS)
        market = self.scanner.scan_assets(interval=timeframe, outputsize=120, assets=assets)
        result = self.futures_module.analyze_market(
            market,
            capital_state=self.load_capital_state(),
            asset=asset,
            execution_mode=execution_mode,
            timeframe=timeframe,
            strategy_name=strategy_name,
        )
        self.latest_futures = deepcopy(result)
        return result

    def execute_futures(self, plan=None, mode="paper", use_trailing_stop=False, trailing_callback_rate=1.2):
        if not isinstance(plan, dict):
            plan = self.latest_futures or self.analyze_futures(execution_mode="paper")
        result = self.execution_service.execute_plan(
            plan,
            mode=mode,
            use_trailing_stop=use_trailing_stop,
            trailing_callback_rate=trailing_callback_rate,
        )
        self.latest_execution = deepcopy(result)
        return result

    def close_futures_trade(self, report):
        return self.execution_service.register_close_report(report)

    def futures_account_snapshot(self, symbol=None):
        if not self.vault.has_credentials():
            return {
                "connected": False,
                "balance": [],
                "positions": [],
                "open_orders": [],
                "order_history": [],
            }
        try:
            positions = self.binance_client.position_risk(symbol=symbol)
            balance = self.binance_client.account_balance()
            open_orders = self.binance_client.open_orders(symbol=symbol) if symbol else []
            order_history = self.binance_client.order_history(symbol=symbol, limit=20) if symbol else []
            return {
                "connected": True,
                "balance": balance,
                "positions": positions,
                "open_orders": open_orders,
                "order_history": order_history,
            }
        except Exception as exc:
            return {
                "connected": True,
                "error": str(exc),
                "balance": [],
                "positions": [],
                "open_orders": [],
                "order_history": [],
            }

    def analytics_snapshot(self):
        summary = self.self_optimizer.summary()
        recent_trades = self.self_optimizer._recent_trades(limit=40)
        curve = []
        running = 0.0
        for idx, trade in enumerate(reversed(recent_trades), start=1):
            running += float(trade.get("pnl", 0.0) or 0.0)
            curve.append({"x": idx, "equity": round(running, 4), "asset": trade.get("asset")})
        return {
            "summary": summary,
            "equity_curve": curve,
            "recent_trades": recent_trades[:20],
        }

    def dashboard_snapshot(self):
        return {
            "active_mode": self.get_mode(),
            "binary": {
                "latest": deepcopy(self.latest_binary),
                "summary": self.self_optimizer.build_mode_summary("BINARY_MODE"),
            },
            "futures": {
                "latest": deepcopy(self.latest_futures),
                "summary": self.self_optimizer.build_mode_summary("FUTURES_MODE"),
                "connection": self.connection_status(),
                "bot": self.bot_service.status(),
                "account": self.futures_account_snapshot(symbol=(self.latest_futures or {}).get("asset")),
            },
            "capital": self.load_capital_state(),
            "analytics": self.analytics_snapshot(),
            "last_execution": deepcopy(self.latest_execution),
            "server_time": int(time.time()),
        }
