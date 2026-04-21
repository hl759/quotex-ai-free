from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Settings:
    # ─── ATIVOS ──────────────────────────────────────────────────────────────
    # RENDER FREE: lista enxuta. Use env var ASSETS_CRYPTO para customizar.
    # Padrão: apenas 3 pares crypto (mais líquidos na Quotex)
    assets_crypto: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_CRYPTO", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT").split(",")
        if s.strip()
    ])

    # Crypto "puro" desativado por padrão no free tier (duplica chamadas)
    assets_pure_crypto: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_PURE_CRYPTO", "").split(",")
        if s.strip()
    ])

    # RENDER FREE: apenas 4 forex principais
    assets_forex: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_FOREX", "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD").split(",")
        if s.strip()
    ])

    # RENDER FREE: apenas GOLD (mais volume)
    assets_metals: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_METALS", "GOLD").split(",")
        if s.strip()
    ])

    # ─── SCANNER ─────────────────────────────────────────────────────────────
    # RENDER FREE: 300s = 5 min entre scans. Mude via env var se quiser.
    passive_interval_seconds: int = int(os.getenv("PASSIVE_INTERVAL_SECONDS", "240"))

    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))

    # RENDER FREE: 1 worker = sem paralelismo, sem burst de requests externos
    scanner_max_workers: int = int(os.getenv("SCANNER_MAX_WORKERS", "1"))

    # ─── UI / POLLING ────────────────────────────────────────────────────────
    # RENDER FREE: frontend atualiza a cada 90s (bem acima do scan_interval)
    ui_auto_refresh_seconds: int = int(os.getenv("UI_AUTO_REFRESH_SECONDS", "90"))
    ui_stale_after_seconds: int = int(os.getenv("UI_STALE_AFTER_SECONDS", "330"))
    ui_force_scan_after_seconds: int = int(os.getenv("UI_FORCE_SCAN_AFTER_SECONDS", "360"))

    # Cooldown entre scans manuais (evita duplo disparo no snapshot endpoint)
    request_scan_min_interval_seconds: int = int(
        os.getenv("REQUEST_SCAN_MIN_INTERVAL_SECONDS", "120")
    )

    signal_min_lead_seconds: int = int(os.getenv("SIGNAL_MIN_LEAD_SECONDS", "18"))

    # ─── QUALIDADE DE DADOS ──────────────────────────────────────────────────
    data_quality_min_operable: float = float(os.getenv("DATA_QUALITY_MIN_OPERABLE", "0.60"))
    data_quality_min_offense: float = float(os.getenv("DATA_QUALITY_MIN_OFFENSE", "0.78"))

    # ─── CAPITAL ─────────────────────────────────────────────────────────────
    default_payout: float = float(os.getenv("DEFAULT_PAYOUT", "0.80"))
    default_risk_pct: float = float(os.getenv("DEFAULT_RISK_PCT", "0.01"))

    # ─── APP ─────────────────────────────────────────────────────────────────
    app_name: str = os.getenv("APP_NAME", "Alpha Hive AI")
    port: int = int(os.getenv("PORT", "10000"))

    run_background_scanner: bool = (
        os.getenv("RUN_BACKGROUND_SCANNER", "1").strip().lower()
        not in ("0", "false", "no")
    )
    scan_route_enabled: bool = (
        os.getenv("SCAN_ROUTE_ENABLED", "1").strip().lower()
        not in ("0", "false", "no")
    )
    scan_trigger_token: str = os.getenv("SCAN_TRIGGER_TOKEN", "").strip()

    # ─── API KEYS ────────────────────────────────────────────────────────────
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
