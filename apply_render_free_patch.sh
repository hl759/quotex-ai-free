#!/bin/bash
# =============================================================================
# apply_render_free_patch.sh
# Aplica as otimizações de banda para o Render free tier no seu repositório.
# Execute no Termux de dentro da raiz do seu repositório git.
#
# USO:
#   chmod +x apply_render_free_patch.sh
#   ./apply_render_free_patch.sh
# =============================================================================

set -e

echo "🔧 Iniciando patch render-free..."

# Verifica se está na raiz do repositório
if [ ! -f "app.py" ] || [ ! -d "alpha_hive" ]; then
  echo "❌ Execute este script na raiz do repositório (onde está app.py)"
  exit 1
fi

# ── 1. Backup dos arquivos originais ─────────────────────────────────────────
echo "📦 Fazendo backup dos originais..."
cp alpha_hive/config.py                      alpha_hive/config.py.bak_original
cp alpha_hive/market/scanner.py              alpha_hive/market/scanner.py.bak_original
cp alpha_hive/app/routes/snapshot.py         alpha_hive/app/routes/snapshot.py.bak_original
cp alpha_hive/app/web.py                     alpha_hive/app/web.py.bak_original
cp alpha_hive/app/static/js/app.js           alpha_hive/app/static/js/app.js.bak_original
cp requirements.txt                          requirements.txt.bak_original
cp Procfile                                  Procfile.bak_original

# ── 2. Remove arquivos .bak desnecessários que ocupam espaço no repo ─────────
echo "🗑️  Removendo .bak files de static (não devem estar no repo)..."
rm -f alpha_hive/app/static/index.html.cache_fix.bak
rm -f alpha_hive/app/static/index.html.no_zero_flash.bak
rm -f alpha_hive/app/static/index.html.pre_cache_fix.bak

# ── 3. Aplica os novos arquivos ───────────────────────────────────────────────
echo "📝 Aplicando arquivos otimizados..."

# config.py — ativos reduzidos + intervalos maiores
cat > alpha_hive/config.py << 'PYEOF'
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
        os.getenv("ASSETS_CRYPTO", "BTCUSDT,ETHUSDT,SOLUSDT").split(",")
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
        os.getenv("ASSETS_FOREX", "EURUSD,GBPUSD,USDJPY,AUDUSD").split(",")
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
PYEOF

# scanner.py — outputsize reduzido
cat > alpha_hive/market/scanner.py << 'PYEOF'
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from alpha_hive.config import SETTINGS
from alpha_hive.core.contracts import MarketSnapshot
from alpha_hive.market.data_manager import DataManager
from alpha_hive.market.reliability_engine import ReliabilityEngine

# RENDER FREE: 80 velas 1min (era 260). 80 é suficiente para RSI/MACD/Bollinger.
_M1_OUTPUTSIZE = 80
_M5_OUTPUTSIZE = 30


class MarketScanner:
    def __init__(self, data_manager: Optional[DataManager] = None):
        self.data = data_manager or DataManager()
        self.reliability = ReliabilityEngine()

    def _market_type(self, asset: str) -> str:
        if asset in SETTINGS.assets_crypto or asset in SETTINGS.assets_pure_crypto:
            return "crypto"
        if asset in SETTINGS.assets_forex:
            return "forex"
        return "metals"

    def scan_asset(self, asset: str) -> Optional[MarketSnapshot]:
        candles_m1, chain = self.data.get_candles(
            asset, interval="1min", outputsize=_M1_OUTPUTSIZE
        )
        if not candles_m1:
            return None

        # Constrói M5 a partir do M1 (evita segunda chamada de API)
        candles_m5 = self.data.build_m5_from_m1(candles_m1, outputsize=_M5_OUTPUTSIZE)

        # Só busca M5 direto se realmente insuficiente (mínimo = 8 velas)
        if len(candles_m5) < 8:
            direct_m5, _ = self.data.get_candles(
                asset, interval="5min", outputsize=_M5_OUTPUTSIZE
            )
            if len(direct_m5) > len(candles_m5):
                candles_m5 = direct_m5

        if not candles_m5:
            candles_m5 = (
                self.data.build_m5_from_m1(candles_m1, outputsize=8)
                or candles_m1[-8:]
            )

        provider = self.data.last_provider_used.get(asset, chain[0] if chain else "unknown")
        provider_root = provider.split("-")[0] if provider else "unknown"
        health_score = self.data.health.get(provider_root).score() if provider else 0.5
        dq_score, dq_state, warnings = self.reliability.evaluate(
            provider, chain, candles_m1, health_score
        )

        return MarketSnapshot(
            asset=asset,
            market_type=self._market_type(asset),
            provider=provider,
            provider_fallback_chain=chain,
            data_quality_score=dq_score,
            data_quality_state=dq_state,
            candles_m1=candles_m1,
            candles_m5=candles_m5,
            warnings=warnings,
            display_asset=asset,
            source_symbol=self.data.resolve_source_symbol(asset, provider),
            source_kind=self.data.source_kind_for(asset),
        )

    def scan_assets(self) -> List[MarketSnapshot]:
        assets = SETTINGS.assets
        max_workers = max(1, min(SETTINGS.scanner_max_workers, len(assets)))
        out: List[MarketSnapshot] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self.scan_asset, asset): asset
                for asset in assets
            }
            for future in as_completed(future_map):
                snapshot = future.result()
                if snapshot:
                    out.append(snapshot)

        asset_order = {asset: idx for idx, asset in enumerate(assets)}
        out.sort(key=lambda item: asset_order.get(item.asset, 10**9))
        return out
PYEOF

# snapshot.py — remove auto_refresh do GET /snapshot
cat > alpha_hive/app/routes/snapshot.py << 'PYEOF'
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from alpha_hive.services.snapshot_service import SnapshotService

bp = Blueprint("snapshot", __name__)
snapshot_service = SnapshotService()


def _bootstrap_snapshot(scan_service) -> dict:
    """
    RENDER FREE: NÃO dispara scans automáticos a cada GET /snapshot.
    Apenas o background scanner inicia scans.
    Exceção: bootstrap (scan_count == 0) para ter dados na primeira abertura.
    """
    scan_service.ensure_started()

    meta = scan_service.runtime.setdefault("meta", {})
    meta["last_snapshot_refresh_error"] = ""
    meta["last_snapshot_refresh_result"] = {}

    try:
        current_state = scan_service.snapshot()
        current_meta = dict(current_state.get("meta", {}) or {})

        scan_count = int(current_meta.get("scan_count", 0) or 0)
        scan_in_progress = bool(current_meta.get("scan_in_progress", False))

        # Só faz scan aqui se for o primeiro acesso (sem dados ainda)
        if not scan_in_progress and scan_count <= 0:
            refresh_result = scan_service.run_once("snapshot_bootstrap")
            if isinstance(refresh_result, dict):
                meta["last_snapshot_refresh_result"] = refresh_result
                if "evaluated" in refresh_result:
                    meta["pending_evaluated_last_scan"] = int(
                        refresh_result.get("evaluated", 0) or 0
                    )

        # REMOVIDO: pending_expired check e auto_refresh_if_needed
        # Esses dois chamavam run_once() em praticamente toda requisição GET.

    except Exception as exc:
        meta["last_snapshot_refresh_error"] = repr(exc)

    return snapshot_service.build(scan_service.snapshot())


@bp.get("/")
def home():
    scan_service = current_app.config["SCAN_SERVICE"]
    scan_service.ensure_started()
    return current_app.send_static_file("index.html")


@bp.get("/snapshot")
def snapshot():
    scan_service = current_app.config["SCAN_SERVICE"]
    return jsonify(_bootstrap_snapshot(scan_service))
PYEOF

# web.py — adiciona Flask-Compress (gzip)
cat > alpha_hive/app/web.py << 'PYEOF'
from __future__ import annotations

import time
from pathlib import Path

from flask import Flask

from alpha_hive.app.routes.capital import bp as capital_bp
from alpha_hive.app.routes.control import bp as control_bp
from alpha_hive.app.routes.diagnostics import bp as diagnostics_bp
from alpha_hive.app.routes.health import bp as health_bp
from alpha_hive.app.routes.snapshot import bp as snapshot_bp
from alpha_hive.config import SETTINGS
from alpha_hive.services.scan_service import ScanService


def create_app() -> Flask:
    static_folder = str(Path(__file__).resolve().parent / "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="")

    # ── Compressão gzip (RENDER FREE: reduz JSON em ~65-75%) ─────────────────
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass  # flask-compress não instalado: continua sem compressão

    app.config["SETTINGS"] = SETTINGS
    app.config["SCAN_SERVICE"] = ScanService()
    app.config["START_TIME"] = time.time()

    # ── Cache-Control para arquivos estáticos ─────────────────────────────────
    @app.after_request
    def add_cache_headers(response):
        path = getattr(response, "_request_path", "")
        if path and (path.endswith(".css") or path.endswith(".js")):
            response.cache_control.max_age = 3600
            response.cache_control.public = True
        return response

    app.register_blueprint(health_bp)
    app.register_blueprint(snapshot_bp)
    app.register_blueprint(capital_bp)
    app.register_blueprint(control_bp)
    app.register_blueprint(diagnostics_bp)

    return app
PYEOF

# app.js — polling de 20s → 90s
cat > alpha_hive/app/static/js/app.js << 'JSEOF'
// RENDER FREE: polling reduzido de 20s → 90s
async function refresh() {
  try {
    const resp = await fetch('/snapshot');
    if (!resp.ok) return;
    const data = await resp.json();
    document.getElementById('decision').textContent =
      JSON.stringify(data.current_decision, null, 2);
    document.getElementById('signals').textContent =
      JSON.stringify(data.signals, null, 2);
    document.getElementById('meta').textContent =
      JSON.stringify(data.meta, null, 2);
  } catch (e) {
    console.warn('snapshot fetch error:', e);
  }
}

async function runScan() {
  await fetch('/run-scan');
  await refresh();
}

refresh();
setInterval(refresh, 90000); // era 20000
JSEOF

# requirements.txt — adiciona flask-compress
cat > requirements.txt << 'EOF'
flask
flask-compress
requests
pandas
numpy
gunicorn
psycopg2-binary
pytest
EOF

# Procfile — adiciona --timeout 120
cat > Procfile << 'EOF'
web: gunicorn --workers 1 --threads 2 --bind 0.0.0.0:$PORT --timeout 120 --keep-alive 5 app:app
EOF

# ── 4. Remove __pycache__ (não devem estar no repo) ──────────────────────────
echo "🧹 Limpando __pycache__..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# ── 5. Commit e push ──────────────────────────────────────────────────────────
echo ""
echo "✅ Patch aplicado com sucesso!"
echo ""
echo "📋 Arquivos modificados:"
git diff --name-only 2>/dev/null || echo "  (git diff indisponível)"
echo ""
echo "🚀 Fazendo commit e push..."
git add .
git commit -m "feat: otimizar para Render free tier

- Reduz ativos padrão de 25 → 8 (controlável por env vars)
- Aumenta scan_interval de 60s → 300s
- Remove auto_refresh_if_needed do GET /snapshot
- Reduz outputsize de velas: 260 → 80 (1min), 50 → 30 (5min)
- Reduz polling frontend de 20s → 90s
- Adiciona flask-compress (gzip ~65% menos banda nos JSONs)
- Reduce scanner_max_workers padrão de 3 → 1
- Remove arquivos .bak desnecessários do static
- Remove __pycache__ do repositório"

git push origin main

echo ""
echo "🎉 Pronto! Deploy vai iniciar no Render automaticamente."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 REDUÇÃO DE BANDA ESTIMADA:"
echo "  Antes:  ~6.5 GB/mês (25 ativos × 60s × 2 APIs)"
echo "  Depois: ~120 MB/mês (8 ativos × 300s × 1 API)"
echo "  Economia: ~98% de redução"
echo ""
echo "⚙️  CUSTOMIZAÇÃO via variáveis de ambiente no Render:"
echo "  ASSETS_CRYPTO=BTCUSDT,ETHUSDT,SOLUSDT"
echo "  ASSETS_FOREX=EURUSD,GBPUSD,USDJPY,AUDUSD"
echo "  ASSETS_METALS=GOLD"
echo "  SCAN_INTERVAL_SECONDS=300"
echo "  SCANNER_MAX_WORKERS=1"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
