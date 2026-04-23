from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Settings:
    # ─── ATIVOS ──────────────────────────────────────────────────────────────
    # Defaults conservadores para instância free: menos ativos = menos RAM/bandwidth.
    # Quem quiser ampliar pode sobrescrever via env vars no Render.
    assets_crypto: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_CRYPTO", "BTCUSDT,ETHUSDT,XRPUSDT").split(",")
        if s.strip()
    ])

    # Instrumentos OTC/nomeados da EBINEX — dados via Yahoo Finance (BTC-USD etc.)
    assets_pure_crypto: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_PURE_CRYPTO", "BITCOIN").split(",")
        if s.strip()
    ])

    # Forex disponíveis na EBINEX
    assets_forex: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_FOREX", "EURUSD,GBPUSD").split(",")
        if s.strip()
    ])

    # Metais
    assets_metals: List[str] = field(default_factory=lambda: [
        s.strip() for s in
        os.getenv("ASSETS_METALS", "").split(",")
        if s.strip()
    ])

    # ─── SCANNER AUTÔNOMO ────────────────────────────────────────────────────
    # A IA escaneia automaticamente a cada scan_interval_seconds.
    # 60s = scan a cada expiração M1. Padrão: 60s para Render free.
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))

    # 1 worker conserva RAM no Render free (512 MB).
    scanner_max_workers: int = int(os.getenv("SCANNER_MAX_WORKERS", "1"))

    # ─── UI ──────────────────────────────────────────────────────────────────
    ui_auto_refresh_seconds: int = int(os.getenv("UI_AUTO_REFRESH_SECONDS", "60"))
    ui_stale_after_seconds: int = int(os.getenv("UI_STALE_AFTER_SECONDS", "300"))
    ui_force_scan_after_seconds: int = int(os.getenv("UI_FORCE_SCAN_AFTER_SECONDS", "120"))

    signal_min_lead_seconds: int = int(os.getenv("SIGNAL_MIN_LEAD_SECONDS", "18"))
    inactivity_timeout_seconds: int = int(os.getenv("INACTIVITY_TIMEOUT_SECONDS", "600"))

    # ─── QUALIDADE DE DADOS ──────────────────────────────────────────────────
    data_quality_min_operable: float = float(os.getenv("DATA_QUALITY_MIN_OPERABLE", "0.60"))
    data_quality_min_offense: float = float(os.getenv("DATA_QUALITY_MIN_OFFENSE", "0.78"))

    # ─── CAPITAL ─────────────────────────────────────────────────────────────
    default_payout: float = float(os.getenv("DEFAULT_PAYOUT", "0.80"))
    default_risk_pct: float = float(os.getenv("DEFAULT_RISK_PCT", "0.01"))

    # ─── APP ─────────────────────────────────────────────────────────────────
    app_name: str = os.getenv("APP_NAME", "Alpha Hive AI")
    port: int = int(os.getenv("PORT", "10000"))

    # Scanner autônomo sempre ativo — pode desligar com RUN_BACKGROUND_SCANNER=0
    run_background_scanner: bool = (
        os.getenv("RUN_BACKGROUND_SCANNER", "1").strip().lower()
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
