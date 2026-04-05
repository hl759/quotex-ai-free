import json
import os
from copy import deepcopy

from storage_paths import STATE_DIR
from json_safe import safe_dump


class HybridModeRouter:
    def __init__(self, binary_module, futures_module, self_optimizer, scanner, capital_state_loader):
        self.binary_module = binary_module
        self.futures_module = futures_module
        self.self_optimizer = self_optimizer
        self.scanner = scanner
        self.capital_state_loader = capital_state_loader
        self.state_path = os.path.join(STATE_DIR, "hybrid_mode_snapshot.json")
        self.state = self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {
            "active_mode": self.self_optimizer.get_active_mode(),
            "last_binary": None,
            "last_futures": None,
        }

    def _save(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(self.state, f)
        os.replace(tmp, self.state_path)

    def get_active_mode(self):
        mode = self.state.get("active_mode") or self.self_optimizer.get_active_mode()
        return self.self_optimizer.set_active_mode(mode) if mode != self.self_optimizer.get_active_mode() else mode

    def set_active_mode(self, mode):
        active = self.self_optimizer.set_active_mode(mode)
        self.state["active_mode"] = active
        self._save()
        return active

    def run_once(self, mode=None, asset=None, execution_mode=None):
        active_mode = str(mode or self.state.get("active_mode") or self.self_optimizer.get_active_mode()).upper().strip()
        if active_mode not in ("BINARY_MODE", "FUTURES_MODE"):
            active_mode = "BINARY_MODE"
        capital_state = self.capital_state_loader()
        market = self.scanner.scan_assets()
        if active_mode == "FUTURES_MODE":
            result = self.futures_module.analyze_market(market, capital_state=capital_state, asset=asset, execution_mode=execution_mode)
            self.state["last_futures"] = deepcopy(result)
        else:
            result = self.binary_module.analyze_market(market, capital_state=capital_state)
            self.state["last_binary"] = deepcopy(result)
        self.state["active_mode"] = active_mode
        self.self_optimizer.set_active_mode(active_mode)
        self._save()
        return result

    def snapshot(self):
        self.state["active_mode"] = self.self_optimizer.get_active_mode()
        self._save()
        return {
            "active_mode": self.state.get("active_mode"),
            "supported_modes": ["BINARY_MODE", "FUTURES_MODE"],
            "last_binary": self.state.get("last_binary"),
            "last_futures": self.state.get("last_futures"),
            "self_optimization": self.self_optimizer.summary(),
        }
