import os

CRYPTO_ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]

FOREX_ASSETS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP"
]

METALS_ASSETS = ["GOLD", "SILVER"]

ASSETS = CRYPTO_ASSETS + FOREX_ASSETS + METALS_ASSETS

# ─── Scanner ─────────────────────────────────
# Crypto (Binance, ilimitado): scan a cada 60s
# Forex (Twelve Data, limitado): varre TODOS os pares a cada scan
SCAN_INTERVAL_SECONDS        = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
TWELVE_SCAN_INTERVAL_SECONDS = int(os.getenv("TWELVE_SCAN_INTERVAL_SECONDS", "300"))  # FIX: era 600 (10min), agora 5min
TWELVE_BATCH_SIZE            = int(os.getenv("TWELVE_BATCH_SIZE", "10"))              # FIX: era 1, agora varre TODOS os 10 pares Forex

# ─── API Keys ────────────────────────────────
TWELVE_API_KEYS = [os.getenv("TWELVE_API_KEY_1", "").strip(), os.getenv("TWELVE_API_KEY_2", "").strip()]
TWELVE_API_KEYS = [k for k in TWELVE_API_KEYS if k]

FINNHUB_API_KEY      = os.getenv("FINNHUB_API_KEY", "").strip()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()

# ─── Limites de crédito Twelve Data ──────────
# FIX CRÍTICO: era 40/dia e freeze em 60 — usava apenas 7.5% dos 800 disponíveis
# Agora: soft limit 350/chave, freeze em 750 — usa 93% dos créditos disponíveis
TWELVE_DAILY_SOFT_LIMIT_PER_KEY = int(os.getenv("TWELVE_DAILY_SOFT_LIMIT_PER_KEY", "350"))  # FIX: era 40
TWELVE_MINUTE_LIMIT_PER_KEY     = int(os.getenv("TWELVE_MINUTE_LIMIT_PER_KEY", "7"))         # FIX: era 1 (limite real é 8/min)
TWELVE_GLOBAL_DAILY_HARD_STOP   = int(os.getenv("TWELVE_GLOBAL_DAILY_HARD_STOP", "750"))     # FIX: era 60

CACHE_TTL_1MIN = int(os.getenv("CACHE_TTL_1MIN", "58"))
CACHE_TTL_5MIN = int(os.getenv("CACHE_TTL_5MIN", "295"))

# FIX: era 30 e 60 — agora alinhado ao novo hard stop
ECONOMY_MODE_AFTER_TOTAL  = int(os.getenv("ECONOMY_MODE_AFTER_TOTAL", "600"))
FREEZE_TWELVE_AFTER_TOTAL = int(os.getenv("FREEZE_TWELVE_AFTER_TOTAL", "750"))

FINNHUB_PAUSE_SECONDS = int(os.getenv("FINNHUB_PAUSE_SECONDS", "120"))
ALPHA_PAUSE_SECONDS   = int(os.getenv("ALPHA_PAUSE_SECONDS", "180"))

# FIX: era 2, agora 3 — mostra os melhores sinais
MAX_SIGNALS = int(os.getenv("MAX_SIGNALS", "3"))

# ─── Trading ─────────────────────────────────
DEFAULT_PAYOUT         = float(os.getenv("DEFAULT_PAYOUT", "0.80"))
DEFAULT_RISK_PCT       = float(os.getenv("DEFAULT_RISK_PCT", "0.01"))
EXECUTION_DELAY_CANDLES = int(os.getenv("EXECUTION_DELAY_CANDLES", "0"))

# ─── Edge Guard ──────────────────────────────
# FIX: era 36 trades para provar edge — sistema ficava bloqueado no início
# Agora: 10 trades suficientes para começar a operar com cautela
EDGE_PROOF_MIN_TRADES   = int(os.getenv("EDGE_PROOF_MIN_TRADES", "10"))      # FIX: era 36
EDGE_SEGMENT_MIN_TRADES = int(os.getenv("EDGE_SEGMENT_MIN_TRADES", "5"))     # FIX: era 8

ADAPTIVE_MIN_TRADES        = int(os.getenv("ADAPTIVE_MIN_TRADES", "15"))     # FIX: era 30
ADAPTIVE_STRONG_MIN_TRADES = int(os.getenv("ADAPTIVE_STRONG_MIN_TRADES", "50"))  # FIX: era 80
ADAPTIVE_PROVEN_MIN_TRADES = int(os.getenv("ADAPTIVE_PROVEN_MIN_TRADES", "100")) # FIX: era 150

# FIX: modo shadow → validation → live
# Começa em validation para gerar sinais desde o início
ALPHA_HIVE_MODE = os.getenv("ALPHA_HIVE_MODE", "live").strip().lower()

EDGE_GUARD_ACTIVE              = os.getenv("EDGE_GUARD_ACTIVE", "1").strip().lower() not in ("0", "false", "no")
EDGE_MIN_PROFIT_FACTOR         = float(os.getenv("EDGE_MIN_PROFIT_FACTOR", "1.02"))       # FIX: era 1.03
EDGE_SEGMENT_MIN_PROFIT_FACTOR = float(os.getenv("EDGE_SEGMENT_MIN_PROFIT_FACTOR", "1.00"))
EDGE_LIVE_MIN_PROB             = float(os.getenv("EDGE_LIVE_MIN_PROB", "0.75"))           # FIX: era 0.80
EDGE_VALIDATION_MIN_PROB       = float(os.getenv("EDGE_VALIDATION_MIN_PROB", "0.52"))     # FIX: era 0.54
EDGE_RECENT_WINDOW             = int(os.getenv("EDGE_RECENT_WINDOW", "20"))
EDGE_RECENT_KILL_WINDOW        = int(os.getenv("EDGE_RECENT_KILL_WINDOW", "12"))
EDGE_RECENT_KILL_EXPECTANCY_R  = float(os.getenv("EDGE_RECENT_KILL_EXPECTANCY_R", "-0.12")) # FIX: era -0.10
EDGE_RECENT_WARN_EXPECTANCY_R  = float(os.getenv("EDGE_RECENT_WARN_EXPECTANCY_R", "-0.05")) # FIX: era -0.04

# ─── Trader Council ──────────────────────────
TRADER_COUNCIL_ACTIVE          = os.getenv("TRADER_COUNCIL_ACTIVE", "1").strip().lower() not in ("0", "false", "no")
TRADER_COUNCIL_SPECIALIST_LIMIT = int(os.getenv("TRADER_COUNCIL_SPECIALIST_LIMIT", "42"))
TRADER_COUNCIL_MEMORY_MIN_CASES = int(os.getenv("TRADER_COUNCIL_MEMORY_MIN_CASES", "4"))  # FIX: era 6

# ─── Bootstrap ───────────────────────────────
# FIX: era 64% confiança mínima — muito exigente sem histórico
# Agora: 58% — gera mais sinais na fase de bootstrap
BOOTSTRAP_ACTIVE              = os.getenv("BOOTSTRAP_ACTIVE", "1").strip().lower() not in ("0", "false", "no")
BOOTSTRAP_MIN_CONFIDENCE      = int(os.getenv("BOOTSTRAP_MIN_CONFIDENCE", "58"))      # FIX: era 64
BOOTSTRAP_MIN_SCORE           = float(os.getenv("BOOTSTRAP_MIN_SCORE", "1.40"))       # FIX: era 1.80
BOOTSTRAP_MAX_TRADES          = int(os.getenv("BOOTSTRAP_MAX_TRADES", "30"))
BOOTSTRAP_WARMUP_MAX_TRADES   = int(os.getenv("BOOTSTRAP_WARMUP_MAX_TRADES", "90"))
BOOTSTRAP_STAKE_MULTIPLIER    = float(os.getenv("BOOTSTRAP_STAKE_MULTIPLIER", "0.16"))
BOOTSTRAP_WARMUP_STAKE_MULTIPLIER = float(os.getenv("BOOTSTRAP_WARMUP_STAKE_MULTIPLIER", "0.28"))

# ─── UI ──────────────────────────────────────
HISTORY_SAVE_LIMIT         = int(os.getenv("HISTORY_SAVE_LIMIT", "30"))
SNAPSHOT_HISTORY_LIMIT     = int(os.getenv("SNAPSHOT_HISTORY_LIMIT", "20"))
UI_AUTO_REFRESH_SECONDS    = int(os.getenv("UI_AUTO_REFRESH_SECONDS", "20"))
UI_STALE_AFTER_SECONDS     = int(os.getenv("UI_STALE_AFTER_SECONDS", "95"))
UI_FORCE_SCAN_AFTER_SECONDS = int(os.getenv("UI_FORCE_SCAN_AFTER_SECONDS", "110"))
UI_CACHE_REFRESH_EVERY_SCANS = int(os.getenv("UI_CACHE_REFRESH_EVERY_SCANS", "6"))
UI_CACHE_REFRESH_MAX_SECONDS = int(os.getenv("UI_CACHE_REFRESH_MAX_SECONDS", "180"))
SCAN_TRIGGER_TOKEN         = os.getenv("SCAN_TRIGGER_TOKEN", "").strip()
SCAN_ROUTE_ENABLED         = os.getenv("SCAN_ROUTE_ENABLED", "1").strip().lower() not in ("0", "false", "no")
SCAN_ALIGN_TO_INTERVAL     = os.getenv("SCAN_ALIGN_TO_INTERVAL", "1").strip().lower() not in ("0", "false", "no")
