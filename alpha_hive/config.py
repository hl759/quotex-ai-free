from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Settings:
    assets_crypto: List[str] = field(default_factory=lambda: [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
    ])

    assets_pure_crypto: List[str] = field(default_factory=lambda: [
        "BITCOIN",
        "ETHEREUM",
        "SOLANA",
        "RIPPLE",
        "CARDANO",
        "DOGECOIN",
    ])

    assets_forex: List[str] = field(default_factory=lambda: [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP"
    ])

    assets_metals: List[str] = field(default_factory=lambda: ["GOLD", "SILVER"])

    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
    ui_auto_refresh_seconds: int = int(os.getenv("UI_AUTO_REFRESH_SECONDS", "20"))
    ui_stale_after_seconds: int = int(os.getenv("UI_STALE_AFTER_SECONDS", "95"))
    ui_force_scan_after_seconds: int = int(os.getenv("UI_FORCE_SCAN_AFTER_SECONDS", "110"))

    data_quality_min_operable: float = float(os.getenv("DATA_QUALITY_MIN_OPERABLE", "0.60"))
    data_quality_min_offense: float = float(os.getenv("DATA_QUALITY_MIN_OFFENSE", "0.78"))

    default_payout: float = float(os.getenv("DEFAULT_PAYOUT", "0.80"))
    default_risk_pct: float = float(os.getenv("DEFAULT_RISK_PCT", "0.01"))

    app_name: str = os.getenv("APP_NAME", "Alpha Hive AI")
    port: int = int(os.getenv("PORT", "10000"))

    scanner_max_workers: int = int(os.getenv("SCANNER_MAX_WORKERS", "3"))

    run_background_scanner: bool = os.getenv("RUN_BACKGROUND_SCANNER", "1").strip().lower() not in ("0", "false", "no")
    scan_route_enabled: bool = os.getenv("SCAN_ROUTE_ENABLED", "1").strip().lower() not in ("0", "false", "no")
    scan_trigger_token: str = os.getenv("SCAN_TRIGGER_TOKEN", "").strip()

    twelvedata_keys: List[str] = field(default_factory=lambda: [
        k for k in [
            os.getenv("TWELVE_API_KEY_1", "").strip(),
            os.getenv("TWELVE_API_KEY_2", "").strip(),
        ] if k
    ])

    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "").strip()
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()

    @property
    def assets(self) -> List[str]:
        return (
            self.assets_crypto
            + self.assets_pure_crypto
            + self.assets_forex
            + self.assets_metals
        )


SETTINGS = Settings()
