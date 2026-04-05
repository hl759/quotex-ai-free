
import os
import threading
import time

from core.security import mask_secret


class InMemoryCredentialVault:
    """
    Backend-only credential vault.

    Prioriza variáveis de ambiente para produção e aceita chaves enviadas pelo painel
    apenas em memória de processo. Nunca devolve o segredo em texto puro.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "api_key": os.getenv("BINANCE_FUTURES_API_KEY", "").strip(),
            "api_secret": os.getenv("BINANCE_FUTURES_API_SECRET", "").strip(),
            "source": "environment" if os.getenv("BINANCE_FUTURES_API_KEY") else "disconnected",
            "connected_at": int(time.time()) if os.getenv("BINANCE_FUTURES_API_KEY") else None,
            "testnet": str(os.getenv("BINANCE_FUTURES_TESTNET", "0")).strip().lower() in ("1", "true", "yes"),
        }

    def connect(self, api_key, api_secret, testnet=False, source="api_panel"):
        api_key = str(api_key or "").strip()
        api_secret = str(api_secret or "").strip()
        if not api_key or not api_secret:
            raise ValueError("api_key_and_secret_required")
        with self._lock:
            self._state.update({
                "api_key": api_key,
                "api_secret": api_secret,
                "source": source,
                "connected_at": int(time.time()),
                "testnet": bool(testnet),
            })
        return self.status()

    def disconnect(self):
        with self._lock:
            self._state.update({
                "api_key": "",
                "api_secret": "",
                "source": "disconnected",
                "connected_at": None,
                "testnet": False,
            })
        return self.status()

    def credentials(self):
        with self._lock:
            return self._state.get("api_key", ""), self._state.get("api_secret", "")

    def has_credentials(self):
        api_key, api_secret = self.credentials()
        return bool(api_key and api_secret)

    def is_testnet(self):
        with self._lock:
            return bool(self._state.get("testnet", False))

    def status(self):
        with self._lock:
            api_key = self._state.get("api_key", "")
            return {
                "connected": bool(self._state.get("api_key") and self._state.get("api_secret")),
                "source": self._state.get("source", "disconnected"),
                "connected_at": self._state.get("connected_at"),
                "api_key_masked": mask_secret(api_key),
                "testnet": bool(self._state.get("testnet", False)),
            }
