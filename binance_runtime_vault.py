import os
import threading


class BinanceRuntimeVault:
    """
    Armazena credenciais apenas em memória durante a execução.
    Em produção no Render, o ideal é usar env vars para credenciais persistentes.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._runtime = {
            "api_key": None,
            "api_secret": None,
            "testnet": None,
        }

    def _masked(self, value):
        if not value:
            return ""
        value = str(value)
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    def set_credentials(self, api_key, api_secret, testnet=None):
        with self._lock:
            self._runtime["api_key"] = str(api_key or "").strip() or None
            self._runtime["api_secret"] = str(api_secret or "").strip() or None
            self._runtime["testnet"] = bool(testnet) if testnet is not None else None
        return self.status()

    def clear_credentials(self):
        with self._lock:
            self._runtime = {
                "api_key": None,
                "api_secret": None,
                "testnet": None,
            }
        return self.status()

    def resolve(self):
        with self._lock:
            runtime_key = self._runtime.get("api_key")
            runtime_secret = self._runtime.get("api_secret")
            runtime_testnet = self._runtime.get("testnet")

        env_key = os.getenv("BINANCE_FUTURES_API_KEY", "").strip() or None
        env_secret = os.getenv("BINANCE_FUTURES_API_SECRET", "").strip() or None
        env_testnet = os.getenv("BINANCE_FUTURES_TESTNET", "0").strip().lower() in ("1", "true", "yes")

        api_key = runtime_key or env_key
        api_secret = runtime_secret or env_secret
        testnet = runtime_testnet if runtime_testnet is not None else env_testnet

        return {
            "api_key": api_key,
            "api_secret": api_secret,
            "testnet": bool(testnet),
        }

    def status(self):
        resolved = self.resolve()
        source = "runtime" if self._runtime.get("api_key") else ("environment" if resolved.get("api_key") else "none")
        return {
            "connected": bool(resolved.get("api_key") and resolved.get("api_secret")),
            "source": source,
            "testnet": bool(resolved.get("testnet")),
            "api_key_masked": self._masked(resolved.get("api_key")),
            "api_secret_present": bool(resolved.get("api_secret")),
        }
