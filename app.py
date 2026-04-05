import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string, request
from json_safe import safe_dump, safe_dumps, to_jsonable
from storage_paths import DATA_DIR, STATE_DIR, migrate_file
from state_store import StateStore

from scanner import MarketScanner
from signal_engine import SignalEngine
from data_manager import DataManager
from learning_engine import LearningEngine
from result_evaluator import ResultEvaluator
from result_engine import ResultEngine
from strategy_lab import StrategyLab
from journal_manager import JournalManager
from decision_engine import DecisionEngine
from edge_audit import EdgeAuditEngine
from edge_guard import EdgeGuardEngine
from specialist_reputation_engine import SpecialistReputationEngine
from storage_governance_engine import StorageGovernanceEngine

FUTURES_AVAILABLE = True
FUTURES_IMPORT_ERROR = ""
try:
    from futures_module import FuturesModule
    from self_optimization_engine import SelfOptimizationEngine
    from binance_runtime_vault import BinanceRuntimeVault
    from binance_broker_service import BinanceBrokerService
    from futures_bot_service import FuturesBotService
except Exception as futures_import_exc:
    FUTURES_AVAILABLE = False
    FUTURES_IMPORT_ERROR = str(futures_import_exc)
    FuturesModule = None
    SelfOptimizationEngine = None
    BinanceRuntimeVault = None
    BinanceBrokerService = None
    FuturesBotService = None

try:
    from adaptive_engine import AdaptiveEngine
except Exception:
    AdaptiveEngine = None

try:
    from memory_engine import MemoryEngine
except Exception:
    MemoryEngine = None

try:
    from market_profile_engine import MarketProfileEngine
except Exception:
    MarketProfileEngine = None

from config import (
    ASSETS, SCAN_INTERVAL_SECONDS, DEFAULT_PAYOUT, HISTORY_SAVE_LIMIT, SNAPSHOT_HISTORY_LIMIT,
    UI_AUTO_REFRESH_SECONDS, UI_STALE_AFTER_SECONDS, UI_FORCE_SCAN_AFTER_SECONDS,
    UI_CACHE_REFRESH_EVERY_SCANS, UI_CACHE_REFRESH_MAX_SECONDS, SCAN_TRIGGER_TOKEN,
    SCAN_ROUTE_ENABLED, SCAN_ALIGN_TO_INTERVAL,
)

app = Flask(__name__)

data_manager = DataManager()
learning = LearningEngine()
scanner = MarketScanner(data_manager, learning)
signal_engine = SignalEngine(learning)
decision_engine = DecisionEngine(learning)
result_evaluator = ResultEvaluator()
result_engine = ResultEngine(result_evaluator)
strategy_lab = StrategyLab()
adaptive_engine = AdaptiveEngine() if AdaptiveEngine else None
memory_engine = MemoryEngine() if MemoryEngine else None
market_profile_engine = MarketProfileEngine() if MarketProfileEngine else None
journal = JournalManager()
edge_audit = EdgeAuditEngine()
edge_guard = EdgeGuardEngine()
specialist_reputation = SpecialistReputationEngine()
self_optimization_engine = SelfOptimizationEngine() if FUTURES_AVAILABLE and SelfOptimizationEngine else None
futures_module = FuturesModule(data_manager, self_optimizer=self_optimization_engine) if FUTURES_AVAILABLE and FuturesModule else None
binance_vault = BinanceRuntimeVault() if FUTURES_AVAILABLE and BinanceRuntimeVault else None
binance_broker = BinanceBrokerService(binance_vault) if FUTURES_AVAILABLE and BinanceBrokerService and binance_vault else None

LATEST_SIGNALS_FILE = os.path.join(STATE_DIR, "latest_signals.json")
SIGNAL_HISTORY_FILE = os.path.join(STATE_DIR, "history.json")
META_FILE = os.path.join(STATE_DIR, "meta.json")
CURRENT_DECISION_FILE = os.path.join(STATE_DIR, "current_decision.json")
PENDING_DECISIONS_FILE = os.path.join(STATE_DIR, "pending_decisions.json")
CAPITAL_STATE_FILE = os.path.join(STATE_DIR, "capital_state.json")

LEGACY_STATE_DIRS = [
    os.path.join(os.getcwd(), "nexus_state"),
    "/tmp/nexus_state",
]
for _name, _dest in {
    "latest_signals.json": LATEST_SIGNALS_FILE,
    "history.json": SIGNAL_HISTORY_FILE,
    "meta.json": META_FILE,
    "current_decision.json": CURRENT_DECISION_FILE,
    "pending_decisions.json": PENDING_DECISIONS_FILE,
    "capital_state.json": CAPITAL_STATE_FILE,
}.items():
    migrate_file(_dest, [os.path.join(base, _name) for base in LEGACY_STATE_DIRS])

state_store = StateStore()
storage_governance = StorageGovernanceEngine(state_store=state_store)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    tmp = path + ".tmp"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(data, f)
        os.replace(tmp, path)
        return True
    except Exception as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        print(f"write_json warning for {path}: {e}", flush=True)
        return False


def bootstrap_scan_count():
    meta_file = read_json(META_FILE, {"scan_count": 0})
    meta_store = state_store.get_json("meta", {"scan_count": 0}) or {"scan_count": 0}
    candidates = [
        meta_file.get("scan_count", 0) if isinstance(meta_file, dict) else 0,
        meta_store.get("scan_count", 0) if isinstance(meta_store, dict) else 0,
        state_store.get_int("scan_count", 0),
        state_store.max_scan_count(),
    ]
    best = 0
    for value in candidates:
        try:
            best = max(best, int(value or 0))
        except Exception:
            continue
    return best

scan_count = bootstrap_scan_count()
scanner_started = False
scanner_lock = threading.Lock()
scan_run_lock = threading.Lock()
ui_cache = {}
ui_cache_ts = 0.0
ui_cache_last_refresh_scan = 0
UI_CACHE_TTL_SECONDS = max(5, int(os.environ.get("ALPHA_HIVE_UI_CACHE_TTL", str(UI_AUTO_REFRESH_SECONDS)) or UI_AUTO_REFRESH_SECONDS))
last_scan_started_ts = 0.0
last_scan_finished_ts = 0.0
last_scan_duration_ms = 0
last_scan_error = ""
last_scan_trigger = "boot"
scan_in_progress = False
next_scan_due_ts = 0.0
last_manual_scan_request_ts = 0.0


def ensure_capital_state():
    default_state = {
        "capital_current": 0.0,
        "capital_peak": 0.0,
        "daily_pnl": 0.0,
        "streak": 0,
        "daily_target_pct": 2.0,
        "daily_stop_pct": 3.0
    }
    try:
        current = state_store.get_json("capital_state", None)
    except Exception as e:
        print(f"ensure_capital_state store read warning: {e}", flush=True)
        current = None
    if not isinstance(current, dict):
        current = read_json(CAPITAL_STATE_FILE, default_state)
    if not isinstance(current, dict):
        current = dict(default_state)
    for key, value in default_state.items():
        current.setdefault(key, value)
    if float(current.get("capital_peak", 0.0) or 0.0) < float(current.get("capital_current", 0.0) or 0.0):
        current["capital_peak"] = float(current.get("capital_current", 0.0) or 0.0)
    write_json(CAPITAL_STATE_FILE, current)
    try:
        state_store.set_json("capital_state", current)
    except Exception as e:
        print(f"ensure_capital_state store write warning: {e}", flush=True)
    return current


def load_capital_state():
    default_state = {
        "capital_current": 0.0,
        "capital_peak": 0.0,
        "daily_pnl": 0.0,
        "streak": 0,
        "daily_target_pct": 2.0,
        "daily_stop_pct": 3.0,
    }
    try:
        current = state_store.get_json("capital_state", None)
    except Exception as e:
        print(f"load_capital_state store read warning: {e}", flush=True)
        current = None
    if not isinstance(current, dict):
        current = read_json(CAPITAL_STATE_FILE, default_state)
    if not isinstance(current, dict):
        current = dict(default_state)
    for key, value in default_state.items():
        current.setdefault(key, value)
    if float(current.get("capital_peak", 0.0) or 0.0) < float(current.get("capital_current", 0.0) or 0.0):
        current["capital_peak"] = float(current.get("capital_current", 0.0) or 0.0)
    return current


def save_capital_state(data):
    current = load_capital_state()
    merged = {
        "capital_current": float(data.get("capital_current", current.get("capital_current", 0.0)) or 0.0),
        "capital_peak": float(data.get("capital_peak", current.get("capital_peak", 0.0)) or 0.0),
        "daily_pnl": float(data.get("daily_pnl", current.get("daily_pnl", 0.0)) or 0.0),
        "streak": int(float(data.get("streak", current.get("streak", 0)) or 0)),
        "daily_target_pct": float(data.get("daily_target_pct", current.get("daily_target_pct", 2.0)) or 2.0),
        "daily_stop_pct": float(data.get("daily_stop_pct", current.get("daily_stop_pct", 3.0)) or 3.0),
    }
    if merged["capital_peak"] < merged["capital_current"]:
        merged["capital_peak"] = merged["capital_current"]
    try:
        write_json(CAPITAL_STATE_FILE, merged)
    except Exception as e:
        print(f"save_capital_state local write warning: {e}", flush=True)
    try:
        state_store.set_json("capital_state", merged)
    except Exception as e:
        print(f"save_capital_state store write warning: {e}", flush=True)
    return merged


def futures_feature_status():
    return {
        "available": bool(FUTURES_AVAILABLE and futures_module is not None and self_optimization_engine is not None),
        "import_error": str(FUTURES_IMPORT_ERROR or ""),
    }


def sync_futures_credentials_from_vault():
    if not futures_feature_status()["available"] or not binance_vault or not futures_module:
        return {"api_key": None, "api_secret": None, "testnet": False}
    resolved = binance_vault.resolve()
    futures_module.api_key = str(resolved.get("api_key") or "").strip()
    futures_module.api_secret = str(resolved.get("api_secret") or "").strip()
    futures_module.base_url = "https://testnet.binancefuture.com" if resolved.get("testnet") else "https://fapi.binance.com"
    return resolved


def _futures_disabled_response(status=503):
    payload = {"ok": False, "error": "futures_module_unavailable", "details": futures_feature_status()}
    return jsonify(to_jsonable(payload)), status


sync_futures_credentials_from_vault()
futures_bot_service = FuturesBotService(scanner, futures_module, load_capital_state) if futures_feature_status()["available"] and FuturesBotService else None


class CapitalAutoTracker:
    def __init__(self):
        self.data_dir = os.environ.get("ALPHA_HIVE_DATA_DIR", "/opt/render/project/src/data")
        self.journal_file = os.path.join(self.data_dir, "alpha_hive_journal.json")

    def _load_journal(self):
        data = state_store.list_collection("journal_trades", limit=4000)
        if data:
            return data if isinstance(data, list) else []
        data = read_json(self.journal_file, [])
        return data if isinstance(data, list) else []

    def _result_value(self, trade):
        return str(trade.get("result", "")).upper()

    def _today_key(self):
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _trade_date_key(self, trade):
        explicit = trade.get("date")
        if explicit:
            return str(explicit)
        return self._today_key()

    def _valid_trades(self, journal_rows):
        return [t for t in journal_rows if self._result_value(t) in ("WIN", "LOSS")]

    def _compute_streak(self, valid_trades):
        if not valid_trades:
            return 0
        streak = 0
        for trade in valid_trades:
            result = self._result_value(trade)
            if result == "WIN":
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif result == "LOSS":
                if streak <= 0:
                    streak -= 1
                else:
                    break
        return streak

    def _compute_daily_pnl(self, valid_trades, capital_current):
        today = self._today_key()
        todays = [t for t in valid_trades if self._trade_date_key(t) == today]
        if not todays:
            return 0.0

        direct = []
        for trade in todays:
            try:
                direct.append(float(trade.get("gross_pnl", 0.0) or 0.0))
            except Exception:
                direct.append(0.0)

        if any(abs(v) > 0 for v in direct):
            return round(sum(direct), 2)

        if capital_current <= 0:
            return 0.0

        unit_risk = max(1.0, round(capital_current * 0.01, 2))
        pnl = 0.0
        for trade in todays:
            pnl += unit_risk if self._result_value(trade) == "WIN" else -unit_risk
        return round(pnl, 2)

    def update(self):
        state = load_capital_state()
        journal_rows = self._load_journal()
        valid = self._valid_trades(journal_rows)

        capital_current = float(state.get("capital_current", 0.0) or 0.0)
        capital_peak = float(state.get("capital_peak", 0.0) or 0.0)

        if valid:
            state["daily_pnl"] = self._compute_daily_pnl(valid, capital_current)
            state["streak"] = self._compute_streak(valid)
        else:
            state["daily_pnl"] = float(state.get("daily_pnl", 0.0) or 0.0)
            state["streak"] = int(float(state.get("streak", 0) or 0))

        if capital_current > capital_peak:
            capital_peak = capital_current
        state["capital_peak"] = round(capital_peak, 2)

        save_capital_state(state)
        return state


capital_auto_tracker = CapitalAutoTracker()
ensure_capital_state()
try:
    storage_governance.maybe_run_maintenance(scan_count=scan_count, force=False)
except Exception as e:
    print(f"storage governance bootstrap warning: {e}", flush=True)


def now_brazil():
    return datetime.utcnow() - timedelta(hours=3)


def _as_list(value):
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _reason_text(lines):
    lines = _as_list(lines)
    return "\n".join(["• " + str(r) for r in lines]) if lines else "Sem detalhes"


def _clean_reason_line(line):
    text = str(line or "").strip().replace("•", "")
    return text[:1].upper() + text[1:] if text else ""


def _pick_reason(lines, keywords=None, exclude_prefixes=None):
    items = [_clean_reason_line(x) for x in _as_list(lines)]
    if exclude_prefixes:
        filtered = []
        for item in items:
            lower = item.lower()
            if any(lower.startswith(prefix.lower()) for prefix in exclude_prefixes):
                continue
            filtered.append(item)
        items = filtered or items
    if keywords:
        for item in items:
            lower = item.lower()
            if any(k.lower() in lower for k in keywords):
                return item
    return items[0] if items else ""


def _compact_regime(regime):
    value = str(regime or "unknown")
    return value if value != "unknown" else "neutro"


def _build_signal_summary(signal, reasons):
    confidence = int(float(signal.get("confidence", 50) or 50))
    regime = _compact_regime(signal.get("regime", "unknown"))
    if confidence >= 85:
        confidence_text = "confiança alta"
    elif confidence >= 74:
        confidence_text = "confiança moderada"
    else:
        confidence_text = "confiança em validação"

    preferred = _pick_reason(
        reasons,
        keywords=["consenso", "contexto", "tendência", "romp", "revers", "mercado", "regime"],
        exclude_prefixes=["boost", "stake", "modo:", "strategy score", "evolução:"]
    )
    main = preferred or f"Leitura {signal.get('signal', 'CALL')} com {confidence_text}."
    points = [
        f"Regime: {regime}",
        f"Confiança: {confidence}%",
    ]
    return {
        "summary_title": "Resumo operacional",
        "summary_main": main,
        "summary_points": points,
    }


def _build_decision_summary(decision, reasons):
    action = str(decision.get("decision", "NAO_OPERAR") or "NAO_OPERAR")
    direction = decision.get("direction")
    regime = _compact_regime(decision.get("regime", "unknown"))
    environment = str(decision.get("environment_type", "unknown") or "unknown")
    council_quality = str(decision.get("council_quality", "neutro") or "neutro")
    head_action = str(decision.get("head_trader_action", "none") or "none")
    behavior_mode = str(decision.get("behavior_mode", "BALANCED") or "BALANCED")
    capital_phase = str(decision.get("capital_phase", "neutral") or "neutral")
    edge_mode = str(decision.get("edge_guard_mode", "validation") or "validation")
    decision_cap = decision.get("edge_guard_decision_cap")
    stake = float(decision.get("suggested_stake", 0.0) or 0.0)
    trend_quality = str(decision.get("trend_quality", "neutra") or "neutra")
    conflict_type = str(decision.get("conflict_type", "neutro") or "neutro")

    if action == "ENTRADA_FORTE":
        main = "Confluência forte liberou entrada com risco controlado."
    elif action == "ENTRADA_CAUTELA":
        main = "Entrada permitida em cautela para validar o contexto com proteção de capital."
    elif action == "OBSERVAR":
        main = "A mesa preferiu observar: contexto ainda não mereceu risco de patrimônio."
    else:
        main = "Entrada vetada para preservar capital diante de contexto fraco ou conflituoso."

    preferred = _pick_reason(
        reasons,
        keywords=["head trader", "edge guard", "orquestração final", "risk dominance final", "discernimento final", "consenso", "contexto com pouca amostra", "nenhuma estratégia forte"],
        exclude_prefixes=["boost", "strategy score", "stake sugerida", "score ajustado", "modo:"]
    )
    if preferred:
        main = preferred

    summary_points = [
        f"Ambiente: {environment} • regime {regime} • tendência {trend_quality}",
        f"Council: {council_quality} • Head Trader: {head_action or 'none'} • conflito {conflict_type}",
        f"Risco: {behavior_mode} • capital {capital_phase} • stake {round(stake, 2)}",
    ]
    if decision_cap:
        summary_points.append(f"Execução estatística: modo {edge_mode} com limite {decision_cap}")
    else:
        summary_points.append(f"Prova estatística: modo {edge_mode}")
    if direction:
        summary_points.insert(0, f"Direção preferida: {direction}")

    title_map = {
        "ENTRADA_FORTE": "Resumo da entrada forte",
        "ENTRADA_CAUTELA": "Resumo da entrada em cautela",
        "OBSERVAR": "Resumo da observação",
        "NAO_OPERAR": "Resumo do veto",
    }
    return {
        "summary_title": title_map.get(action, "Resumo operacional"),
        "summary_main": main,
        "summary_points": summary_points,
    }


def normalize_signals(signals):
    out = []
    for s in signals:
        analysis = now_brazil()
        entry = analysis + timedelta(minutes=1)
        expiration = entry + timedelta(minutes=1)
        reasons = _as_list(s.get("reason", []))
        signal_summary = _build_signal_summary(s, reasons)
        out.append({
            "asset": s.get("asset", "N/A"),
            "signal": s.get("signal", "CALL"),
            "score": s.get("score", 0),
            "confidence": s.get("confidence", 50),
            "confidence_label": s.get("confidence_label", "MÉDIO"),
            "provider": s.get("provider", "auto"),
            "analysis_time": analysis.strftime("%H:%M"),
            "entry_time": entry.strftime("%H:%M"),
            "expiration": expiration.strftime("%H:%M"),
            "reasons": reasons,
            "reason_text": _reason_text(reasons),
            "summary_title": signal_summary.get("summary_title", "Resumo operacional"),
            "summary_main": signal_summary.get("summary_main", "Sem resumo"),
            "summary_points": signal_summary.get("summary_points", []),
            "regime": s.get("regime", "unknown")
        })
    return out


def decorate_decision(decision):
    analysis = now_brazil()
    entry = analysis + timedelta(minutes=1)
    expiration = entry + timedelta(minutes=1)
    reasons = _as_list(decision.get("reasons", []))
    summary = _build_decision_summary(decision, reasons)
    return {
        "asset": decision.get("asset", "MERCADO"),
        "decision": decision.get("decision", "NAO_OPERAR"),
        "direction": decision.get("direction"),
        "score": decision.get("score", 0),
        "confidence": decision.get("confidence", 50),
        "regime": decision.get("regime", "unknown"),
        "analysis_time": analysis.strftime("%H:%M"),
        "entry_time": entry.strftime("%H:%M"),
        "expiration": expiration.strftime("%H:%M"),
        "reasons": reasons,
        "reason_text": _reason_text(reasons),
        "summary_title": summary.get("summary_title", "Resumo operacional"),
        "summary_main": summary.get("summary_main", "Sem resumo"),
        "summary_points": summary.get("summary_points", []),
        "setup_id": decision.get("setup_id"),
        "context_id": decision.get("context_id"),
        "strategy_name": decision.get("strategy_name", "none"),
        "evolution_variant": decision.get("evolution_variant", "base"),
        "suggested_stake": decision.get("suggested_stake", 0.0),
        "risk_pct": decision.get("risk_pct", 0.0),
        "payout": DEFAULT_PAYOUT,
        "date": analysis.strftime("%Y-%m-%d"),
        "market_narrative": decision.get("market_narrative", "none"),
        "trend_quality": decision.get("trend_quality", "neutra"),
        "breakout_quality": decision.get("breakout_quality", "ausente"),
        "conflict_type": decision.get("conflict_type", "neutro"),
        "environment_type": decision.get("environment_type", "unknown"),
        "discernment_quality": decision.get("discernment_quality", "aceitavel"),
        "anti_pattern_risk": decision.get("anti_pattern_risk", "unknown"),
        "behavior_mode": decision.get("behavior_mode", "BALANCED"),
        "behavior_aggressiveness": decision.get("behavior_aggressiveness", "normal"),
        "capital_phase": decision.get("capital_phase", "neutral"),
        "edge_guard_mode": decision.get("edge_guard_mode", "validation"),
        "edge_guard_decision_cap": decision.get("edge_guard_decision_cap"),
        "edge_guard_stake_multiplier": decision.get("edge_guard_stake_multiplier", 1.0),
        "transition_probability": decision.get("transition_probability", "low"),
        "next_environment": decision.get("next_environment", "unknown"),
        "trend_m1": decision.get("trend_m1", "neutral"),
        "trend_m5": decision.get("trend_m5", "neutral"),
        "breakout": decision.get("breakout", False),
        "rejection": decision.get("rejection", False),
        "volatility": decision.get("volatility", False),
        "moved_too_fast": decision.get("moved_too_fast", False),
        "is_sideways": decision.get("is_sideways", False),
        "pattern": decision.get("pattern"),
        "analysis_session": decision.get("analysis_session", analysis.strftime("%H:%M")),
        "council_quality": decision.get("council_quality", "neutro"),
        "council_consensus_direction": decision.get("council_consensus_direction"),
        "head_trader_action": decision.get("head_trader_action", "none"),
        "trader_council": decision.get("trader_council", {}),
        "council_participants": decision.get("council_participants", []),
        "case_memory": decision.get("case_memory", {}),
    }


def _decision_uid(item):
    explicit_uid = str(item.get('uid') or '').strip()
    if explicit_uid:
        return explicit_uid

    unique_issued_at = str(item.get('issued_at_ms') or item.get('issued_at') or '').strip()
    if unique_issued_at:
        return f"{item.get('asset','N/A')}-{item.get('direction','N/A')}-{item.get('analysis_time','--:--')}-{item.get('entry_time','--:--')}-{item.get('expiration','--:--')}-{unique_issued_at}"

    return f"{item.get('asset','N/A')}-{item.get('direction','N/A')}-{item.get('analysis_time','--:--')}-{item.get('entry_time','--:--')}-{item.get('expiration','--:--')}"


def enqueue_pending_decision(current_decision, matched_market):
    if not current_decision:
        return
    if current_decision.get("decision") not in ("ENTRADA_FORTE", "ENTRADA_CAUTELA"):
        return
    if not matched_market:
        return

    pending = read_json(PENDING_DECISIONS_FILE, [])
    existing = {item.get("uid") for item in pending if isinstance(item, dict)}

    issued_at_ms = int(time.time() * 1000)
    record = {
        "issued_at_ms": issued_at_ms,
        "uid": _decision_uid({**current_decision, "issued_at_ms": issued_at_ms}),
        "asset": current_decision.get("asset"),
        "signal": current_decision.get("direction"),
        "score": current_decision.get("score", 0),
        "confidence": current_decision.get("confidence", 0),
        "analysis_time": current_decision.get("analysis_time"),
        "entry_time": current_decision.get("entry_time"),
        "expiration": current_decision.get("expiration"),
        "setup_id": current_decision.get("setup_id"),
        "context_id": current_decision.get("context_id"),
        "strategy_name": current_decision.get("strategy_name", "none"),
        "evolution_variant": current_decision.get("evolution_variant", "base"),
        "regime": current_decision.get("regime", "unknown"),
        "stake_value": current_decision.get("suggested_stake", 0.0),
        "risk_pct": current_decision.get("risk_pct", 0.0),
        "payout": float(current_decision.get("payout", DEFAULT_PAYOUT) or DEFAULT_PAYOUT),
        "date": current_decision.get("date") or now_brazil().strftime("%Y-%m-%d"),
        "market_narrative": current_decision.get("market_narrative", "none"),
        "trend_quality": current_decision.get("trend_quality", "neutra"),
        "breakout_quality": current_decision.get("breakout_quality", "ausente"),
        "conflict_type": current_decision.get("conflict_type", "neutro"),
        "environment_type": current_decision.get("environment_type", "unknown"),
        "discernment_quality": current_decision.get("discernment_quality", "aceitavel"),
        "anti_pattern_risk": current_decision.get("anti_pattern_risk", "unknown"),
        "trend_m1": current_decision.get("trend_m1", "neutral"),
        "trend_m5": current_decision.get("trend_m5", "neutral"),
        "breakout": current_decision.get("breakout", False),
        "rejection": current_decision.get("rejection", False),
        "volatility": current_decision.get("volatility", False),
        "moved_too_fast": current_decision.get("moved_too_fast", False),
        "is_sideways": current_decision.get("is_sideways", False),
        "pattern": current_decision.get("pattern"),
        "analysis_session": current_decision.get("analysis_session"),
        "council_quality": current_decision.get("council_quality", "neutro"),
        "council_consensus_direction": current_decision.get("council_consensus_direction"),
        "head_trader_action": current_decision.get("head_trader_action", "none"),
        "trader_council": current_decision.get("trader_council", {}),
        "council_participants": current_decision.get("council_participants", []),
        "case_memory": current_decision.get("case_memory", {}),
    }

    if record["uid"] not in existing:
        pending.append(record)
        write_json(PENDING_DECISIONS_FILE, pending)


def register_all_learning_outputs(signal, result_data):
    result_value = str(result_data.get("result", "")).upper()
    setup_id = signal.get("setup_id")
    context_id = signal.get("context_id")
    strategy_name = signal.get("strategy_name", "none")
    regime = signal.get("regime", "unknown")

    try:
        learning.register_result(signal, result_data)
    except Exception as e:
        print("Learning register error:", e, flush=True)

    if setup_id:
        try:
            strategy_lab.register_result(setup_id, result_value)
        except Exception as e:
            print("StrategyLab register error:", e, flush=True)

    if memory_engine and context_id:
        try:
            memory_engine.register_result(context_id, result_value)
        except Exception as e:
            print("MemoryEngine register error:", e, flush=True)

    if adaptive_engine:
        try:
            adaptive_engine.register_result(strategy_name, regime, result_value)
        except Exception as e:
            print("AdaptiveEngine register error:", e, flush=True)

    if market_profile_engine:
        try:
            market_profile_engine.register_result(regime, result_value)
        except Exception as e:
            print("MarketProfileEngine register error:", e, flush=True)

    journal_payload = {
        "uid": signal.get("uid"),
        "asset": signal.get("asset"),
        "signal": signal.get("signal"),
        "strategy_name": strategy_name,
        "regime": regime,
        "analysis_time": signal.get("analysis_time"),
        "entry_time": signal.get("entry_time"),
        "expiration": signal.get("expiration"),
        "score": signal.get("score", 0),
        "confidence": signal.get("confidence", 0),
        "result": result_value,
        "setup_id": setup_id,
        "context_id": context_id,
        "evolution_variant": signal.get("evolution_variant", "base"),
        "stake": result_data.get("stake", signal.get("stake_value", 0.0)),
        "risk_pct": signal.get("risk_pct", 0.0),
        "payout": result_data.get("payout", signal.get("payout", DEFAULT_PAYOUT)),
        "gross_pnl": result_data.get("gross_pnl", 0.0),
        "gross_r": result_data.get("gross_r", 0.0),
        "breakeven_winrate": result_data.get("breakeven_winrate", 0.0),
        "entry_price": result_data.get("entry_price"),
        "exit_price": result_data.get("exit_price"),
        "entry_candle_time": result_data.get("entry_candle_time"),
        "exit_candle_time": result_data.get("exit_candle_time"),
        "evaluation_mode": result_data.get("evaluation_mode", "candle_close"),
        "date": signal.get("date") or now_brazil().strftime("%Y-%m-%d"),
        "market_narrative": signal.get("market_narrative"),
        "trend_quality": signal.get("trend_quality"),
        "breakout_quality": signal.get("breakout_quality"),
        "conflict_type": signal.get("conflict_type"),
        "environment_type": signal.get("environment_type"),
        "discernment_quality": signal.get("discernment_quality"),
        "anti_pattern_risk": signal.get("anti_pattern_risk"),
        "trend_m1": signal.get("trend_m1"),
        "trend_m5": signal.get("trend_m5"),
        "breakout": signal.get("breakout"),
        "rejection": signal.get("rejection"),
        "volatility": signal.get("volatility"),
        "moved_too_fast": signal.get("moved_too_fast"),
        "is_sideways": signal.get("is_sideways"),
        "pattern": signal.get("pattern"),
        "analysis_session": signal.get("analysis_session"),
        "council_quality": signal.get("council_quality"),
        "council_consensus_direction": signal.get("council_consensus_direction"),
        "head_trader_action": signal.get("head_trader_action"),
    }

    try:
        journal.add_trade(journal_payload)
    except Exception as e:
        print("Journal add_trade error:", e, flush=True)

    try:
        edge_audit.record_trade(signal, result_data)
    except Exception as e:
        print("Edge audit record error:", e, flush=True)

    try:
        specialist_reputation.register_trade(signal, result_data)
    except Exception as e:
        print("Specialist reputation register error:", e, flush=True)

    try:
        self_optimization_engine.register_binary_outcome(signal, result_data)
    except Exception as e:
        print("Self optimization binary register error:", e, flush=True)


def process_pending_decisions(market):
    pending = read_json(PENDING_DECISIONS_FILE, [])
    if not pending:
        return {"processed": 0, "remaining": 0}

    now_str = now_brazil().strftime("%H:%M")
    still_pending = []
    processed = 0

    for signal in pending:
        expiration = str(signal.get("expiration", "99:99"))
        if expiration > now_str:
            still_pending.append(signal)
            continue

        signal_asset = str(signal.get("asset") or "").strip().upper()
        matched_asset = next(
            (
                item for item in market
                if str(item.get("asset") or "").strip().upper() == signal_asset
            ),
            None,
        )
        if not matched_asset:
            still_pending.append(signal)
            continue

        result_data = result_engine.evaluate_expired_signal(signal, matched_asset.get("candles", []))
        if result_data:
            register_all_learning_outputs(signal, result_data)
            processed += 1
        else:
            still_pending.append(signal)

    write_json(PENDING_DECISIONS_FILE, still_pending)
    return {"processed": processed, "remaining": len(still_pending)}


def save_state(signals, history, current_decision, scans):
    trimmed_history = history[:max(1, HISTORY_SAVE_LIMIT)]
    write_json(LATEST_SIGNALS_FILE, signals)
    write_json(SIGNAL_HISTORY_FILE, trimmed_history)
    write_json(CURRENT_DECISION_FILE, current_decision)
    previous_meta = read_json(META_FILE, {})
    age_seconds = 0 if not last_scan_finished_ts else max(0, int(time.time() - last_scan_finished_ts))
    meta_payload = {
        "last_scan": now_brazil().strftime("%H:%M:%S"),
        "scan_count": scans,
        "state_dir": STATE_DIR,
        "data_dir": DATA_DIR,
        "boot_restored_from": previous_meta.get("scan_count", 0),
        "storage_backend": state_store.backend_name,
        "storage_target": state_store.backend_target if state_store.backend_name == "sqlite" else "postgres",
        "scan_in_progress": scan_in_progress,
        "last_scan_duration_ms": int(last_scan_duration_ms or 0),
        "last_scan_error": str(last_scan_error or ""),
        "last_scan_trigger": str(last_scan_trigger or "loop"),
        "last_scan_age_seconds": age_seconds,
        "next_scan_due_in_seconds": max(0, int(next_scan_due_ts - time.time())) if next_scan_due_ts else SCAN_INTERVAL_SECONDS,
        "ui_auto_refresh_seconds": UI_AUTO_REFRESH_SECONDS,
        "ui_stale_after_seconds": UI_STALE_AFTER_SECONDS,
        "ui_force_scan_after_seconds": UI_FORCE_SCAN_AFTER_SECONDS,
    }
    write_json(META_FILE, meta_payload)
    state_store.set_json("meta", meta_payload)
    state_store.append_scan({
        "signals": signals,
        "history": trimmed_history,
        "current_decision": current_decision,
        "meta": meta_payload,
    }, scans)


def load_state():
    signals = read_json(LATEST_SIGNALS_FILE, [])
    history = read_json(SIGNAL_HISTORY_FILE, [])
    current_decision = read_json(CURRENT_DECISION_FILE, {})
    meta = read_json(META_FILE, {"last_scan": "--", "scan_count": 0})
    if signals or history or current_decision:
        return signals, history, current_decision, meta
    recovered = state_store.last_snapshot() or {}
    if isinstance(recovered, dict):
        return (
            recovered.get("signals", []),
            (recovered.get("history", []) or [])[:max(1, HISTORY_SAVE_LIMIT)],
            recovered.get("current_decision", {}),
            recovered.get("meta", meta),
        )
    return signals, history, current_decision, meta


def get_ui_cache(force=False):
    global ui_cache, ui_cache_ts, ui_cache_last_refresh_scan
    now_ts = time.time()
    if not force and ui_cache and (now_ts - ui_cache_ts) < UI_CACHE_TTL_SECONDS:
        return ui_cache
    cached = state_store.get_json("ui_cache", {}) if not force else {}
    if not force and isinstance(cached, dict) and cached and (now_ts - ui_cache_ts) < (UI_CACHE_TTL_SECONDS * 2):
        ui_cache = cached
        return ui_cache
    data = {}
    try:
        data["learning_stats"] = journal.stats()
    except Exception as e:
        print(f"ui_cache learning_stats warning: {e}", flush=True)
        data["learning_stats"] = {"total": 0, "wins": 0, "loss": 0, "winrate": 0.0}
    try:
        data["best_assets"] = journal.best_assets()
    except Exception as e:
        print(f"ui_cache best_assets warning: {e}", flush=True)
        data["best_assets"] = []
    try:
        data["best_hours"] = journal.best_hours()
    except Exception as e:
        print(f"ui_cache best_hours warning: {e}", flush=True)
        data["best_hours"] = []
    try:
        data["specialist_leaders"] = specialist_reputation.snapshot(limit=12)
    except Exception as e:
        print(f"ui_cache specialist_leaders warning: {e}", flush=True)
        data["specialist_leaders"] = []
    ui_cache = data
    ui_cache_ts = now_ts
    ui_cache_last_refresh_scan = scan_count
    try:
        state_store.set_json("ui_cache", data)
    except Exception as e:
        print(f"ui_cache store warning: {e}", flush=True)
    return data


def get_snapshot(light=True):
    signals, history, current_decision, meta = load_state()
    capital_state = load_capital_state()
    cached = get_ui_cache(force=False)
    last_age = 0 if not last_scan_finished_ts else max(0, int(time.time() - last_scan_finished_ts))
    snapshot = {
        "signals": signals,
        "history": history[:max(1, SNAPSHOT_HISTORY_LIMIT)],
        "current_decision": current_decision,
        "meta": {
            "last_scan": meta.get("last_scan", "--"),
            "scan_count": meta.get("scan_count", 0),
            "signal_count": len(signals),
            "asset_count": len(ASSETS),
            "state_dir": meta.get("state_dir", STATE_DIR),
            "data_dir": meta.get("data_dir", DATA_DIR),
            "db_path": state_store.db_path,
            "storage_backend": state_store.backend_name,
            "storage_target": meta.get("storage_target", state_store.backend_target if state_store.backend_name == "sqlite" else "postgres"),
            "boot_restored_from": meta.get("boot_restored_from", 0),
            "durable_ready": memory_integrity_status().get("durable_ready", False),
            "scan_in_progress": bool(scan_in_progress),
            "last_scan_age_seconds": int(meta.get("last_scan_age_seconds", last_age) or last_age),
            "last_scan_duration_ms": int(meta.get("last_scan_duration_ms", last_scan_duration_ms) or last_scan_duration_ms or 0),
            "last_scan_error": str(meta.get("last_scan_error", last_scan_error) or last_scan_error or ""),
            "last_scan_trigger": str(meta.get("last_scan_trigger", last_scan_trigger) or last_scan_trigger or "loop"),
            "next_scan_due_in_seconds": int(meta.get("next_scan_due_in_seconds", max(0, int(next_scan_due_ts - time.time())) if next_scan_due_ts else SCAN_INTERVAL_SECONDS) or 0),
            "ui_auto_refresh_seconds": int(meta.get("ui_auto_refresh_seconds", UI_AUTO_REFRESH_SECONDS) or UI_AUTO_REFRESH_SECONDS),
            "ui_stale_after_seconds": int(meta.get("ui_stale_after_seconds", UI_STALE_AFTER_SECONDS) or UI_STALE_AFTER_SECONDS),
            "ui_force_scan_after_seconds": int(meta.get("ui_force_scan_after_seconds", UI_FORCE_SCAN_AFTER_SECONDS) or UI_FORCE_SCAN_AFTER_SECONDS),
        },
        "learning_stats": cached.get("learning_stats", {"total": 0, "wins": 0, "loss": 0, "winrate": 0.0}),
        "best_assets": cached.get("best_assets", []),
        "best_hours": cached.get("best_hours", []),
        "capital_state": capital_state,
        "specialist_leaders": cached.get("specialist_leaders", []),
    }
    if not light:
        try:
            snapshot["edge_report"] = edge_audit.compute_report()
        except Exception as e:
            snapshot["edge_report"] = {"error": str(e)}
        try:
            snapshot["edge_guard"] = edge_guard.evaluate(asset="GLOBAL", regime="global", strategy_name="global", analysis_time=None, proposed_decision="OBSERVAR", proposed_score=0.0, proposed_confidence=50)
        except Exception as e:
            snapshot["edge_guard"] = {"error": str(e)}
    return snapshot



def memory_integrity_status():
    meta_file = read_json(META_FILE, {"scan_count": 0})
    meta_store = state_store.get_json("meta", {"scan_count": 0}) or {"scan_count": 0}
    snapshot = state_store.last_snapshot() or {}
    scan_sources = {
        "meta_file_scan_count": int((meta_file or {}).get("scan_count", 0) or 0) if isinstance(meta_file, dict) else 0,
        "meta_store_scan_count": int((meta_store or {}).get("scan_count", 0) or 0) if isinstance(meta_store, dict) else 0,
        "kv_scan_count": int(state_store.get_int("scan_count", 0) or 0),
        "max_scan_count": int(state_store.max_scan_count() or 0),
        "runtime_scan_count": int(scan_count or 0),
    }
    active_backend = state_store.backend_name
    requested_backend = getattr(state_store, "requested_backend", active_backend)
    has_postgres = active_backend == "postgres"
    render_service = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_EXTERNAL_URL"))
    durable_ready = has_postgres
    warnings = []
    if requested_backend == "postgres" and active_backend != "postgres":
        warnings.append("postgres_requested_but_fell_back_to_sqlite")
    if active_backend != "postgres":
        warnings.append("storage_backend_is_not_postgres")
    if render_service and active_backend != "postgres":
        warnings.append("render_local_filesystem_is_ephemeral")
    if os.path.exists(os.path.join(DATA_DIR, "alpha_hive_state.db")):
        warnings.append("local_sqlite_file_present")
    if os.path.exists(os.path.join(DATA_DIR, "alpha_hive_journal.json")):
        warnings.append("local_json_journal_present")
    return {
        "durable_ready": durable_ready,
        "backend": active_backend,
        "requested_backend": requested_backend,
        "backend_target": state_store.backend_target if active_backend == "sqlite" else "postgres",
        "database_url_configured": bool(os.getenv("ALPHA_HIVE_DATABASE_URL") or os.getenv("DATABASE_URL")),
        "postgres_fallback_reason": getattr(state_store, "fallback_reason", None),
        "postgres_last_error": getattr(state_store, "last_error", None),
        "render_environment_detected": render_service,
        "scan_sources": scan_sources,
        "last_snapshot_present": bool(snapshot),
        "scanner_in_progress": bool(scan_in_progress),
        "last_scan_age_seconds": 0 if not last_scan_finished_ts else max(0, int(time.time() - last_scan_finished_ts)),
        "last_scan_duration_ms": int(last_scan_duration_ms or 0),
        "last_scan_error": str(last_scan_error or ""),
        "next_scan_due_in_seconds": max(0, int(next_scan_due_ts - time.time())) if next_scan_due_ts else 0,
        "warning_count": len(warnings),
        "warnings": warnings,
        "recommended_action": (
            "Postgres requested but unavailable; app fell back to sqlite safely" if requested_backend == "postgres" and active_backend != "postgres"
            else ("Configure ALPHA_HIVE_DATABASE_URL / DATABASE_URL to a Postgres database" if not durable_ready else "Persistence looks durable")
        ),
    }


def _compute_next_scan_due(now_ts=None, immediate=False):
    now_ts = now_ts or time.time()
    if immediate:
        return now_ts + 1.0
    interval = max(5, int(SCAN_INTERVAL_SECONDS or 60))
    if SCAN_ALIGN_TO_INTERVAL:
        return ((int(now_ts) // interval) + 1) * interval
    return now_ts + interval


def _should_refresh_ui_cache_after_scan():
    if scan_count <= 2:
        return True
    if scan_count - ui_cache_last_refresh_scan >= max(1, UI_CACHE_REFRESH_EVERY_SCANS):
        return True
    if (time.time() - ui_cache_ts) >= max(30, UI_CACHE_REFRESH_MAX_SECONDS):
        return True
    return False


def run_scan_once(trigger="loop"):
    global scan_count, last_scan_started_ts, last_scan_finished_ts, last_scan_duration_ms
    global last_scan_error, last_scan_trigger, scan_in_progress, next_scan_due_ts, last_manual_scan_request_ts

    if not scan_run_lock.acquire(blocking=False):
        return {"ok": False, "skipped": True, "reason": "scan_already_running", "scan_count": scan_count}

    started_ts = time.time()
    last_scan_started_ts = started_ts
    last_scan_trigger = str(trigger or "loop")
    last_scan_error = ""
    scan_in_progress = True
    if trigger != "loop":
        last_manual_scan_request_ts = started_ts

    try:
        market = scanner.scan_assets()

        pending_summary = process_pending_decisions(market)
        capital_auto_tracker.update()

        decision_candidates = []
        analysis_time = now_brazil().strftime("%H:%M")
        current_weekday = now_brazil().weekday()
        capital_state = load_capital_state()

        for item in market:
            indicators = dict(item.get("indicators", {}))
            indicators["analysis_time"] = analysis_time
            indicators["weekday"] = current_weekday
            indicators.update(capital_state)
            decision = decision_engine.decide(item.get("asset"), indicators)
            decision["provider"] = item.get("provider", "auto")
            decision_candidates.append((decision, item))

        if decision_candidates:
            decision_candidates.sort(key=lambda x: (x[0].get("score", 0), x[0].get("confidence", 0)), reverse=True)
            best_decision_raw, matched_market = decision_candidates[0]
        else:
            best_decision_raw, matched_market = {
                "asset": "MERCADO",
                "decision": "NAO_OPERAR",
                "direction": None,
                "score": 0,
                "confidence": 50,
                "regime": "unknown",
                "reasons": ["Sem dados suficientes no momento"],
                "setup_id": None,
                "strategy_name": "none"
            }, None

        display_decision = decorate_decision(best_decision_raw)
        current_decision = dict(display_decision)
        raw_signals = signal_engine.generate_signals_from_decision(best_decision_raw)
        signals = normalize_signals(raw_signals if raw_signals else [])
        for signal in signals:
            signal["analysis_time"] = current_decision.get("analysis_time")
            signal["entry_time"] = current_decision.get("entry_time")
            signal["expiration"] = current_decision.get("expiration")
        enqueue_pending_decision(current_decision, matched_market)

        history = read_json(SIGNAL_HISTORY_FILE, [])
        if signals:
            history = signals + history

        scan_count += 1
        finished_ts = time.time()
        last_scan_finished_ts = finished_ts
        last_scan_duration_ms = int((finished_ts - started_ts) * 1000)
        next_scan_due_ts = _compute_next_scan_due(finished_ts, immediate=False)
        save_state(signals, history, display_decision, scan_count)
        try:
            storage_governance.maybe_run_maintenance(scan_count=scan_count)
        except Exception as e:
            print(f"storage governance warning: {e}", flush=True)
        try:
            if (pending_summary or {}).get("processed", 0) > 0 or _should_refresh_ui_cache_after_scan():
                get_ui_cache(force=True)
        except Exception as e:
            print(f"ui_cache refresh warning: {e}", flush=True)

        print(
            f"Scan #{scan_count} | Signals: {len(signals)} | Decision: {display_decision['decision']} | Asset: {display_decision['asset']} | Execution Mirror: {current_decision['decision']} | Trigger: {trigger} | Took: {last_scan_duration_ms}ms",
            flush=True
        )
        return {
            "ok": True,
            "skipped": False,
            "scan_count": scan_count,
            "signal_count": len(signals),
            "decision": current_decision.get("decision"),
            "asset": current_decision.get("asset"),
            "duration_ms": last_scan_duration_ms,
            "trigger": trigger,
        }
    except Exception as e:
        last_scan_error = str(e)
        print("Scanner error:", e, flush=True)
        return {"ok": False, "skipped": False, "reason": "scanner_error", "error": str(e), "scan_count": scan_count}
    finally:
        scan_in_progress = False
        next_scan_due_ts = _compute_next_scan_due(time.time(), immediate=False)
        scan_run_lock.release()



def scanner_loop():
    global next_scan_due_ts
    now_ts = time.time()
    signals, history, current_decision, meta = load_state()
    last_scan_text = str((meta or {}).get("last_scan", "") or "").strip()
    meta_age = 999999
    try:
        meta_age = max(0, int(now_ts - os.path.getmtime(META_FILE)))
    except Exception:
        meta_age = 999999
    bootstrap_immediate = scan_count <= 0 or not last_scan_text or meta_age >= max(75, SCAN_INTERVAL_SECONDS + 10)
    next_scan_due_ts = _compute_next_scan_due(now_ts, immediate=bootstrap_immediate)

    while True:
        try:
            now_ts = time.time()
            wait_seconds = max(0.2, next_scan_due_ts - now_ts)
            if wait_seconds > 0.3:
                time.sleep(min(wait_seconds, 1.0))
                continue
            run_scan_once("loop")
            next_scan_due_ts = _compute_next_scan_due(time.time(), immediate=False)
        except Exception as e:
            print("Scanner loop error:", e, flush=True)
            next_scan_due_ts = _compute_next_scan_due(time.time() + 2, immediate=False)
            time.sleep(2)

def ensure_scanner_started():
    global scanner_started
    if scanner_started:
        return
    with scanner_lock:
        if scanner_started:
            return
        threading.Thread(target=scanner_loop, daemon=True).start()
        scanner_started = True


def _snapshot_is_empty(signals=None, history=None, current_decision=None, meta=None):
    signals = signals if isinstance(signals, list) else []
    history = history if isinstance(history, list) else []
    current_decision = current_decision if isinstance(current_decision, dict) else {}
    meta = meta if isinstance(meta, dict) else {}

    if signals or history:
        return False
    if str(current_decision.get("decision") or "").strip():
        return False
    if str(current_decision.get("asset") or "").strip():
        return False
    if int(meta.get("scan_count", 0) or 0) > 0:
        return False
    return True


def ensure_bootstrap_snapshot(force=False):
    signals, history, current_decision, meta = load_state()
    if scan_in_progress:
        return signals, history, current_decision, meta
    if force or _snapshot_is_empty(signals, history, current_decision, meta):
        result = run_scan_once("bootstrap")
        if not result.get("ok") and result.get("reason") != "scan_already_running":
            try:
                print(f"bootstrap snapshot warning: {result}", flush=True)
            except Exception:
                pass
        signals, history, current_decision, meta = load_state()
    return signals, history, current_decision, meta


HTML_PAGE = """
<!DOCTYPE html>
<html lang='pt-BR'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Alpha Hive AI • Premium Mobile</title>
<style>
:root{
  --bg:#030812;
  --bg2:#071627;
  --panel:#08111f;
  --card:#0b1424;
  --card2:#0d1828;
  --stroke:rgba(114,255,237,.14);
  --stroke-strong:rgba(114,255,237,.28);
  --text:#eef6ff;
  --muted:#90a5c6;
  --soft:#5f7393;
  --teal:#5ff5dc;
  --cyan:#66d7ff;
  --blue:#4ca9ff;
  --green:#59ff8f;
  --gold:#ffcc59;
  --red:#ff6f7d;
  --purple:#9563ff;
  --shadow:0 18px 50px rgba(0,0,0,.48);
  --glow:0 0 0 1px rgba(114,255,237,.09), 0 0 24px rgba(78,214,255,.12), inset 0 1px 0 rgba(255,255,255,.04);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:radial-gradient(circle at top,#0a233a 0,#03101d 26%,#030812 60%,#02050a 100%);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;overflow-x:hidden}
body{min-height:100vh;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
button,input,select,textarea{font:inherit}
button{appearance:none;-webkit-appearance:none}
body:before,body:after{content:"";position:fixed;inset:auto;pointer-events:none;z-index:0;border-radius:999px;filter:blur(55px);opacity:.35}
body:before{width:220px;height:220px;left:-80px;top:90px;background:rgba(58,184,255,.18)}
body:after{width:220px;height:220px;right:-80px;top:340px;background:rgba(111,74,255,.16)}
.app{position:relative;z-index:1;max-width:480px;margin:0 auto;padding:16px 14px calc(124px + env(safe-area-inset-bottom,0px))}
.shell{position:relative;isolation:isolate;overflow:visible;border:1px solid rgba(106,225,255,.12);background:linear-gradient(180deg,rgba(7,17,29,.92),rgba(3,8,18,.98));border-radius:28px;padding:16px;box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.04)}
.shell:before{content:"";position:absolute;inset:0;border-radius:28px;padding:1px;background:linear-gradient(135deg,rgba(97,255,230,.30),rgba(96,145,255,.05),rgba(149,99,255,.20));-webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}
.brand-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start}
.brand{display:flex;gap:14px;align-items:center}
.logo-wrap{width:68px;height:68px;border-radius:22px;background:linear-gradient(180deg,rgba(79,212,255,.25),rgba(98,254,214,.12));display:flex;align-items:center;justify-content:center;box-shadow:var(--glow)}
.logo-wrap img{width:48px;height:48px;object-fit:contain}
.brand h1{margin:0;font-size:26px;line-height:1;font-weight:900;letter-spacing:-.03em}
.brand h1 .ai{color:var(--teal)}
.brand p{margin:8px 0 0;font-size:11px;line-height:1.25;color:#9cb1cf;letter-spacing:.22em;text-transform:uppercase}
.right-stack{display:flex;flex-direction:column;gap:10px;align-items:stretch}
.live-pill,.refresh-btn,.mini-badge,.status-pill,.top-pill,.save-btn,.dock-btn,.ghost-btn{position:relative;z-index:3;border-radius:999px;border:1px solid rgba(95,245,220,.14);background:linear-gradient(180deg,rgba(11,31,40,.95),rgba(7,18,27,.95));color:#e9fffc;box-shadow:var(--glow)}
.live-pill{padding:14px 18px;font-weight:900;font-size:14px;letter-spacing:.03em;color:#b4fff3;white-space:nowrap}
.refresh-btn{padding:14px 18px;background:linear-gradient(180deg,#143a63,#0c2844);color:#ecf6ff;font-weight:800;font-size:14px;cursor:pointer;border-color:rgba(117,182,255,.18);pointer-events:auto;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.top-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}
.top-pill{padding:14px 14px;border-radius:20px;background:linear-gradient(180deg,rgba(9,20,33,.96),rgba(8,16,26,.96))}
.top-pill .k{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#8ca2c2}
.top-pill .v{font-size:17px;font-weight:850;margin-top:7px;color:#f4fbff}
.hero-card,.panel-card,.overview-card,.list-card,.metric-card,.timeline-card,.performance-card,.mini-card,.decision-solo{position:relative;z-index:1;background:linear-gradient(180deg,rgba(8,16,28,.98),rgba(5,11,20,.98));border:1px solid rgba(106,225,255,.10);border-radius:24px;box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03)}
.hero-card{margin-top:16px;padding:16px;overflow:hidden}
.hero-card:before,.panel-card:before,.overview-card:before,.decision-solo:before{content:"";position:absolute;inset:0;border-radius:inherit;padding:1px;background:linear-gradient(130deg,rgba(95,245,220,.28),rgba(96,145,255,.08),rgba(149,99,255,.16));-webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}
.hero-kicker,.section-kicker{font-size:12px;letter-spacing:.14em;color:#b9cadf;text-transform:uppercase;font-weight:800;margin-bottom:12px}
.hero-head{display:flex;justify-content:space-between;align-items:start;gap:10px}
.asset-title{font-size:17px;font-weight:900;letter-spacing:.02em;margin:0}
.asset-meta{margin-top:6px;color:#91a6c5;font-size:12px}
.action-badge{display:inline-flex;align-items:center;gap:8px;padding:14px 18px;border-radius:18px;background:linear-gradient(180deg,rgba(29,77,63,.95),rgba(18,46,41,.95));border:1px solid rgba(95,245,220,.24);box-shadow:0 0 0 1px rgba(95,245,220,.08),0 0 20px rgba(95,245,220,.10);font-weight:900;font-size:13px;letter-spacing:.03em;color:#dffff7;text-transform:uppercase}
.action-badge.call{background:linear-gradient(180deg,rgba(28,77,61,.96),rgba(16,42,35,.98))}
.action-badge.put{background:linear-gradient(180deg,rgba(58,47,95,.96),rgba(28,25,50,.98));border-color:rgba(149,99,255,.26)}
.action-badge.block{background:linear-gradient(180deg,rgba(66,27,34,.96),rgba(37,13,18,.98));border-color:rgba(255,111,125,.24)}
.action-badge.hold{background:linear-gradient(180deg,rgba(62,56,25,.96),rgba(32,28,10,.98));border-color:rgba(255,204,89,.24);color:#ffe7ad}
.stake-chip{display:inline-flex;padding:9px 14px;border-radius:16px;background:rgba(17,27,42,.95);border:1px solid rgba(106,225,255,.10);color:#d4e7ff;font-size:13px;margin-top:10px}
.score-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}
.score-tile,.timing-tile,.stat-tile,.asset-pill,.hour-pill{background:linear-gradient(180deg,rgba(10,20,33,.95),rgba(8,15,25,.95));border:1px solid rgba(105,175,255,.10);border-radius:20px;padding:14px}
.score-tile .label,.timing-tile .label,.stat-tile .label,.detail-line .label{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#90a6c6}
.score-tile .value{font-size:20px;font-weight:900;margin-top:8px}
.score-bar{height:10px;background:rgba(255,255,255,.06);border-radius:999px;overflow:hidden;margin-top:12px}
.score-bar span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--teal),#b0ffe4);box-shadow:0 0 18px rgba(95,245,220,.32)}
.timing-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}
.timing-tile .value{font-size:16px;font-weight:850;margin-top:8px}
.summary-grid{display:grid;grid-template-columns:1fr;gap:14px;margin-top:14px}
.panel-card{padding:16px}
.panel-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px}
.panel-head h3{margin:0;font-size:15px;letter-spacing:.06em;text-transform:uppercase}
.mini-badge{padding:7px 12px;font-size:11px;font-weight:800;color:#a9fff2;background:linear-gradient(180deg,rgba(29,77,63,.92),rgba(15,45,38,.94))}
.detail-lines{display:grid;gap:10px}
.detail-line{display:flex;justify-content:space-between;align-items:center;padding:14px 14px;border-radius:18px;background:linear-gradient(90deg,rgba(10,22,35,.98),rgba(10,18,27,.98));border:1px solid rgba(105,175,255,.10)}
.detail-line .value{font-size:16px;font-weight:900}
.detail-line.call .value{color:var(--green)}
.detail-line.risk .value{color:var(--gold)}
.detail-line.exec .value{color:#7ed6ff}
.scan-box{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:170px;overflow:hidden}
.scan-radar{width:132px;height:132px;border-radius:50%;position:relative;background:radial-gradient(circle,rgba(75,255,227,.16) 0,rgba(75,255,227,.05) 38%,rgba(75,255,227,.02) 64%,transparent 70%);border:1px solid rgba(95,245,220,.12);box-shadow:0 0 30px rgba(95,245,220,.12), inset 0 0 30px rgba(95,245,220,.08)}
.scan-radar:before,.scan-radar:after{content:"";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);border-radius:50%;border:1px solid rgba(95,245,220,.08)}
.scan-radar:before{width:88px;height:88px}.scan-radar:after{width:40px;height:40px}
.scan-radar .dot{position:absolute;width:12px;height:12px;border-radius:50%;background:var(--teal);left:50%;top:50%;transform:translate(-50%,-50%);box-shadow:0 0 24px rgba(95,245,220,.65)}
.scan-readout .time{font-size:38px;font-weight:900;line-height:1}.scan-readout .sub{margin-top:10px;color:#9ab0ce;font-size:13px;line-height:1.35}
.learn-card{margin-top:16px;padding:16px;border-radius:26px;background:linear-gradient(180deg,rgba(8,16,28,.98),rgba(4,10,18,.98));border:1px solid rgba(116,98,255,.12);box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.04)}
.learn-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
.learn-title{font-size:18px;font-weight:900}.learn-title small{display:block;margin-top:4px;color:#92a7c5;font-size:12px;font-weight:600}
.ghost-btn{padding:10px 14px;font-size:12px;font-weight:800;color:#eef6ff;background:linear-gradient(180deg,rgba(23,30,49,.94),rgba(12,16,27,.96));cursor:pointer;pointer-events:auto;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.learn-stats{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.stat-tile .value{font-size:28px;font-weight:900;margin-top:10px}
.stat-tile.positive .value{color:var(--green)}
.stat-tile.negative .value{color:#ff7f8b}
.performance-row{display:grid;grid-template-columns:1fr;gap:12px;margin-top:14px}
.performance-card{padding:16px}
.ring-wrap{display:flex;align-items:center;gap:14px}
.ring{width:128px;height:128px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--teal) 0deg,var(--cyan) 180deg,rgba(255,255,255,.08) 180deg);position:relative;box-shadow:0 0 24px rgba(95,245,220,.16)}
.ring:before{content:"";position:absolute;inset:14px;border-radius:50%;background:linear-gradient(180deg,#07121e,#050b14);border:1px solid rgba(255,255,255,.04)}
.ring-inner{position:relative;z-index:1;text-align:center}.ring-inner .big{font-size:28px;font-weight:900}.ring-inner .small{font-size:11px;letter-spacing:.16em;color:#9ab0ce;text-transform:uppercase;margin-top:4px}
.performance-side{flex:1;display:grid;gap:10px}.side-row{display:flex;justify-content:space-between;align-items:center;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,.06)}
.side-row:last-child{border-bottom:none;padding-bottom:0}.side-row .k{color:#95aac7;font-size:12px}.side-row .v{font-weight:850}
.trend-card{margin-top:14px;padding:14px;border-radius:20px;background:linear-gradient(180deg,rgba(10,20,33,.95),rgba(8,15,25,.95));border:1px solid rgba(105,175,255,.10)}
.sparkline{height:92px;border-radius:14px;background:
 linear-gradient(180deg,rgba(255,255,255,.03),transparent),
 linear-gradient(90deg,transparent 0,transparent 8%,rgba(255,255,255,.05) 8%,rgba(255,255,255,.05) 9%,transparent 9%,transparent 17%,rgba(255,255,255,.05) 17%,rgba(255,255,255,.05) 18%,transparent 18%),
 linear-gradient(180deg,transparent 0,transparent 19%,rgba(255,255,255,.05) 19%,rgba(255,255,255,.05) 20%,transparent 20%,transparent 39%,rgba(255,255,255,.05) 39%,rgba(255,255,255,.05) 40%,transparent 40%,transparent 59%,rgba(255,255,255,.05) 59%,rgba(255,255,255,.05) 60%,transparent 60%,transparent 79%,rgba(255,255,255,.05) 79%,rgba(255,255,255,.05) 80%,transparent 80%);
 position:relative;overflow:hidden}
.sparkline svg{width:100%;height:100%}
.bottom-metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}
.metric-card{padding:14px;border-radius:20px}
.metric-card .value{font-size:24px;font-weight:900;margin-top:8px}
.metric-card small{color:#91a6c5}
.bottom-dock{position:fixed;left:50%;transform:translateX(-50%);bottom:max(10px, env(safe-area-inset-bottom,0px));width:min(calc(100vw - 20px), 452px);margin:0;padding:8px;border-radius:24px;background:rgba(4,9,16,.78);border:1px solid rgba(105,175,255,.09);backdrop-filter:blur(16px);box-shadow:0 18px 50px rgba(0,0,0,.45);display:flex;gap:8px;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;-webkit-overflow-scrolling:touch;touch-action:pan-x;z-index:40}
.bottom-dock::-webkit-scrollbar{display:none}
.dock-btn{flex:0 0 auto;min-width:104px;padding:14px 16px;font-weight:850;font-size:15px;color:#c5d4e9;cursor:pointer;pointer-events:auto;touch-action:manipulation;-webkit-tap-highlight-color:transparent;white-space:nowrap}
.dock-btn.active{background:linear-gradient(180deg,rgba(37,99,103,.98),rgba(15,57,67,.98));color:#ecfffc;border-color:rgba(95,245,220,.24);box-shadow:0 0 0 1px rgba(95,245,220,.12),0 0 28px rgba(95,245,220,.12)}
.panel{display:none;margin-top:18px;position:relative;z-index:1}.panel.active{display:block}
.list-grid{display:grid;gap:12px}
.decision-solo{padding:16px}
.empty{padding:24px;text-align:center;border-radius:18px;border:1px dashed rgba(108,145,185,.22);color:#93a7c5;background:rgba(8,16,27,.72)}
.signal-head,.decision-head{display:flex;justify-content:space-between;align-items:start;gap:10px}
.signal-card,.history-card,.rank-card,.hour-card{padding:16px;border-radius:24px;background:linear-gradient(180deg,rgba(8,16,28,.98),rgba(4,10,18,.98));border:1px solid rgba(106,225,255,.10);box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03)}
.asset-name{font-size:28px;font-weight:900;letter-spacing:-.03em}
.badge{display:inline-flex;align-items:center;justify-content:center;padding:11px 14px;border-radius:16px;font-size:13px;font-weight:900;text-transform:uppercase;border:1px solid rgba(255,255,255,.10)}
.badge.call{background:linear-gradient(180deg,rgba(29,77,63,.95),rgba(15,45,38,.95));color:#d6fff7;border-color:rgba(95,245,220,.22)}
.badge.put{background:linear-gradient(180deg,rgba(59,45,102,.95),rgba(28,21,52,.95));color:#ebe4ff;border-color:rgba(149,99,255,.22)}
.badge.hold{background:linear-gradient(180deg,rgba(62,56,25,.95),rgba(32,28,10,.95));color:#ffe4a9;border-color:rgba(255,204,89,.22)}
.badge.block{background:linear-gradient(180deg,rgba(66,27,34,.95),rgba(37,13,18,.95));color:#ffd0d4;border-color:rgba(255,111,125,.22)}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}
.advanced-box{margin-top:14px;border-radius:18px;border:1px solid rgba(105,175,255,.12);background:rgba(7,14,24,.72);overflow:hidden}
.advanced-box summary{list-style:none;cursor:pointer;padding:14px 16px;font-weight:850;color:#dff5ff}.advanced-box summary::-webkit-details-marker{display:none}.advanced-box .reason{padding:0 16px 16px;color:#9fb5d3;line-height:1.55;font-size:13px;white-space:pre-wrap}
.summary-card{padding:16px;border-radius:20px;background:linear-gradient(180deg,rgba(8,16,28,.98),rgba(4,10,18,.98));border:1px solid rgba(105,175,255,.10);margin-top:14px}
.summary-kicker{font-size:12px;letter-spacing:.14em;color:#9bb0cf;text-transform:uppercase;font-weight:800;margin-bottom:10px}
.summary-main{font-size:31px;line-height:1.08;font-weight:900;letter-spacing:-.03em;margin-bottom:14px}
.summary-points{display:grid;gap:9px}.summary-point{display:flex;gap:10px;color:#cce2ff;line-height:1.45}.summary-point .dot{color:var(--teal)}
.advanced-tip{margin-top:12px;color:#8298b6;font-size:12px;line-height:1.45}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.field{display:grid;gap:6px}.field label{font-size:12px;color:#9ab0ce}.field input,.field select{width:100%;border-radius:16px;padding:13px 14px;background:#0b1626;border:1px solid rgba(106,225,255,.12);color:#f4f9ff;font-size:15px;outline:none}.save-btn{margin-top:12px;padding:14px 18px;font-weight:900;color:#eff9ff;cursor:pointer;background:linear-gradient(180deg,#1a4f88,#11355a);pointer-events:auto;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.save-status{margin-top:10px;color:#94abca;font-size:13px}
.hidden{display:none!important}
@media (min-width: 700px){
  .app{max-width:1020px;padding:22px 22px 136px}
  .shell{padding:22px}
  .summary-grid{grid-template-columns:1.15fr .85fr}
  .timing-grid{grid-template-columns:repeat(4,1fr)}
  .learn-stats{grid-template-columns:repeat(4,1fr)}
  .performance-row{grid-template-columns:1.2fr .8fr}
  .bottom-metrics{grid-template-columns:repeat(4,1fr)}
  .bottom-dock{width:min(calc(100vw - 40px), 980px)}
}
</style>
</head>
<body>
<div class='app'>
  <div class='shell'>
    <div class='brand-row'>
      <div class='brand'>
        <div class='logo-wrap' style='font-size:34px'>🐝</div>
        <div>
          <h1>Alpha Hive <span class='ai'>AI</span></h1>
          <p>Inteligência coletiva • edição premium</p>
        </div>
      </div>
      <div class='right-stack'>
        <div id='liveBadge' class='live-pill'>● ESCANEANDO</div>
        <button id='refreshBtn' class='refresh-btn' onclick='refreshSnapshot(false)'>↻ Atualizar agora</button>
      </div>
    </div>

    <div class='top-grid'>
      <div class='top-pill'><div class='k'>Ativo</div><div class='v' id='top_asset_value'>--</div></div>
      <div class='top-pill'><div class='k'>Regime</div><div class='v' id='top_regime_value'>--</div></div>
      <div class='top-pill'><div class='k'>Conexão</div><div class='v' id='top_connection_value'>Modo live</div></div>
    </div>

    <div class='panel active' id='dashboard'>
      <div class='hero-card'>
        <div class='hero-kicker'>Decisão da IA</div>
        <div id='dashboard_decision'></div>
      </div>

      <div class='timing-grid'>
        <div class='timing-tile'><div class='label'>Análise</div><div class='value' id='dash_analysis'>--:--</div></div>
        <div class='timing-tile'><div class='label'>Entrada</div><div class='value' id='dash_entry'>--:--</div></div>
        <div class='timing-tile'><div class='label'>Expiração</div><div class='value' id='dash_expiration'>--:--</div></div>
        <div class='timing-tile'><div class='label'>Regime</div><div class='value' id='dash_regime'>--</div></div>
      </div>

      <div class='summary-grid'>
        <div class='panel-card'>
          <div class='panel-head'><h3>Resumo operacional</h3><div class='mini-badge' id='dash_health_badge'>Nível saudável</div></div>
          <div id='dashboard_summary' class='detail-lines'></div>
        </div>
        <div class='panel-card'>
          <div class='panel-head'><h3>Último scan</h3><div class='mini-badge'>AO VIVO</div></div>
          <div class='scan-box'>
            <div class='scan-radar'><div class='dot'></div></div>
            <div class='scan-readout'>
              <div class='time' id='scan_age_big'>00:00</div>
              <div class='sub' id='scan_sub'>Escaneando mercado...</div>
            </div>
          </div>
        </div>
      </div>

      <div class='learn-card'>
        <div class='learn-head'>
          <div>
            <div class='learn-title'>Aprendizado da IA<small>Acompanhamento do motor adaptativo</small></div>
          </div>
          <button class='ghost-btn' onclick="showTab('stats', document.querySelector('[data-tab=stats]'))">Ver detalhes</button>
        </div>
        <div class='learn-stats'>
          <div class='stat-tile'><div class='label'>Total avaliadas</div><div class='value' id='stats_total'>0</div></div>
          <div class='stat-tile positive'><div class='label'>Win rate</div><div class='value' id='stats_wr'>0%</div></div>
          <div class='stat-tile positive'><div class='label'>Wins</div><div class='value' id='stats_wins'>0</div></div>
          <div class='stat-tile negative'><div class='label'>Loss</div><div class='value' id='stats_loss'>0</div></div>
        </div>
        <div class='performance-row'>
          <div class='trend-card'>
            <div class='panel-head'><h3>Desempenho recente</h3><div class='mini-badge' id='trend_badge'>Tendência estável</div></div>
            <div class='sparkline'>
              <svg viewBox='0 0 320 92' preserveAspectRatio='none'>
                <defs>
                  <linearGradient id='lineGrad' x1='0' y1='0' x2='1' y2='0'>
                    <stop offset='0%' stop-color='#4ca9ff'/>
                    <stop offset='100%' stop-color='#5ff5dc'/>
                  </linearGradient>
                </defs>
                <path d='M0 72 C20 68, 30 40, 52 45 S88 77, 110 62 S145 38, 170 46 S205 74, 226 55 S268 29, 320 18' fill='none' stroke='url(#lineGrad)' stroke-width='3' stroke-linecap='round'/>
                <path d='M0 92 L0 72 C20 68, 30 40, 52 45 S88 77, 110 62 S145 38, 170 46 S205 74, 226 55 S268 29, 320 18 L320 92 Z' fill='rgba(95,245,220,.10)'/>
              </svg>
            </div>
          </div>
          <div class='performance-card'>
            <div class='panel-head'><h3>Desempenho geral</h3><div class='mini-badge'>7 dias</div></div>
            <div class='ring-wrap'>
              <div class='ring' id='wr_ring'><div class='ring-inner'><div class='big' id='wr_ring_text'>0%</div><div class='small'>Win rate</div></div></div>
              <div class='performance-side'>
                <div class='side-row'><div class='k'>Scans</div><div class='v' id='side_scans'>0</div></div>
                <div class='side-row'><div class='k'>Sinais</div><div class='v' id='side_signals'>0</div></div>
                <div class='side-row'><div class='k'>Ativos</div><div class='v' id='side_assets'>0</div></div>
                <div class='side-row'><div class='k'>Atualização</div><div class='v' id='side_update'>--:--</div></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class='bottom-dock'>
      <button class='dock-btn active' data-tab='dashboard' onclick="showTab('dashboard', this)">⌂ Dashboard</button>
      <button class='dock-btn' data-tab='signals' onclick="showTab('signals', this)">⚡ Sinais</button>
      <button class='dock-btn' data-tab='decision' onclick="showTab('decision', this)">🧠 Decisão</button>
      <button class='dock-btn' data-tab='history' onclick="showTab('history', this)">📋 Histórico</button>
      <button class='dock-btn' data-tab='stats' onclick="showTab('stats', this)">📊 Stats</button>
      <button class='dock-btn' data-tab='assets' onclick="showTab('assets', this)">🏆 Ativos</button>
      <button class='dock-btn' data-tab='hours' onclick="showTab('hours', this)">⏰ Horários</button>
      <button class='dock-btn' data-tab='futures' onclick="showTab('futures', this)">🚀 Futures</button>
      <button class='dock-btn' data-tab='capital' onclick="showTab('capital', this)">💰 Capital</button>
    </div>

    <div class='panel' id='signals'>
      <div class='panel-card'><div class='panel-head'><h3>Sinais atuais</h3><div class='mini-badge'>Mesa operável</div></div><div id='signals_container' class='list-grid'></div></div>
    </div>
    <div class='panel' id='decision'>
      <div class='decision-solo'><div class='panel-head'><h3>Decisão do momento</h3><div class='mini-badge'>Motor inteligente</div></div><div id='decision_container'></div></div>
    </div>
    <div class='panel' id='history'>
      <div class='panel-card'><div class='panel-head'><h3>Histórico recente</h3><div class='mini-badge'>Últimas leituras</div></div><div id='history_container' class='list-grid'></div></div>
    </div>
    <div class='panel' id='stats'>
      <div class='panel-card'><div class='panel-head'><h3>Aprendizado e performance</h3><div class='mini-badge'>IA adaptativa</div></div><div id='stats_panel_container'></div></div>
    </div>
    <div class='panel' id='assets'>
      <div class='panel-card'><div class='panel-head'><h3>Melhores ativos</h3><div class='mini-badge'>Ranking</div></div><div id='assets_container' class='list-grid'></div></div>
    </div>
    <div class='panel' id='hours'>
      <div class='panel-card'><div class='panel-head'><h3>Melhores horários</h3><div class='mini-badge'>Janela ideal</div></div><div id='hours_container' class='list-grid'></div></div>
    </div>
    <div class='panel' id='futures'>
      <div class='panel-card'>
        <div class='panel-head'><h3>Binance Futures</h3><div class='mini-badge'>Automação</div></div>
        <div class='form-grid'>
          <div class='field'><label>API Key</label><input id='f_api_key' type='text' autocomplete='off' placeholder='Backend only'></div>
          <div class='field'><label>Secret Key</label><input id='f_api_secret' type='password' autocomplete='off' placeholder='Backend only'></div>
          <div class='field'><label>Symbol</label><input id='f_symbol' type='text' value='BTCUSDT'></div>
          <div class='field'><label>Timeframe</label><select id='f_timeframe'><option value='1m'>1 minuto</option><option value='5m'>5 minutos</option></select></div>
          <div class='field'><label>Execution</label><select id='f_execution_mode'><option value='paper'>Paper</option><option value='live'>Live</option></select></div>
          <div class='field'><label>Testnet</label><select id='f_testnet'><option value='1'>Ligado</option><option value='0'>Desligado</option></select></div>
          <div class='field'><label>Leverage</label><input id='f_leverage' type='number' min='1' step='1' value='3'></div>
          <div class='field'><label>Risco por trade %</label><input id='f_risk_pct' type='number' min='0.1' step='0.1' value='0.6'></div>
          <div class='field'><label>Max trades/dia</label><input id='f_max_trades' type='number' min='1' step='1' value='3'></div>
          <div class='field'><label>Poll segundos</label><input id='f_poll_seconds' type='number' min='20' step='5' value='45'></div>
        </div>
        <div style='display:flex;gap:10px;flex-wrap:wrap;margin-top:12px'>
          <button class='save-btn' onclick='futuresConnect()'>Conectar</button>
          <button class='ghost-btn' onclick='futuresDisconnect()'>Desconectar</button>
          <button class='ghost-btn' onclick='futuresAnalyze()'>Analisar agora</button>
          <button class='save-btn' onclick='futuresStartBot()'>Start bot</button>
          <button class='ghost-btn' onclick='futuresStopBot()'>Stop bot</button>
        </div>
        <div id='f_connection_status' class='save-status'></div>
      </div>
      <div class='panel-card' style='margin-top:14px'>
        <div class='panel-head'><h3>Plano atual</h3><div class='mini-badge'>Execução</div></div>
        <div id='f_plan_container'></div>
      </div>
      <div class='panel-card' style='margin-top:14px'>
        <div class='panel-head'><h3>Conta e posições</h3><div class='mini-badge'>Exchange</div></div>
        <div id='f_account_container' class='advanced-tip'>Sem conexão.</div>
        <div id='f_positions_container' class='list-grid' style='margin-top:12px'></div>
        <div id='f_orders_container' class='list-grid' style='margin-top:12px'></div>
      </div>
      <div class='panel-card' style='margin-top:14px'>
        <div class='panel-head'><h3>Bot status</h3><div class='mini-badge'>Runtime</div></div>
        <div id='f_bot_status' class='advanced-tip'>Parado.</div>
        <div id='f_bot_logs' class='advanced-tip' style='margin-top:12px;white-space:pre-wrap'></div>
      </div>
    </div>

    <div class='panel' id='capital'>
      <div class='panel-card'>
        <div class='panel-head'><h3>Capital da IA</h3><div class='mini-badge'>Mesa premium</div></div>
        <div class='form-grid'>
          <div class='field'><label>Capital atual</label><input id='capital_current' type='number' step='0.01' min='0'></div>
          <div class='field'><label>Pico da banca</label><input id='capital_peak' type='number' step='0.01' min='0'></div>
          <div class='field'><label>PnL do dia</label><input id='daily_pnl' type='number' step='0.01'></div>
          <div class='field'><label>Sequência</label><input id='streak' type='number' step='1'></div>
          <div class='field'><label>Meta diária %</label><input id='daily_target_pct' type='number' step='0.1' min='0'></div>
          <div class='field'><label>Stop diário %</label><input id='daily_stop_pct' type='number' step='0.1' min='0'></div>
        </div>
        <button id='saveCapitalBtn' class='save-btn' onclick='saveCapitalState()'>Salvar capital</button>
        <div id='capital_status' class='save-status'></div>
      </div>
    </div>
  </div>
</div>
<script>
const initialSnapshot = {{ snapshot_json|safe }} || null;
let autoRefreshHandle = null;
let autoRefreshSeconds = (initialSnapshot && initialSnapshot.meta && initialSnapshot.meta.ui_auto_refresh_seconds) || 20;
let staleAfterSeconds = (initialSnapshot && initialSnapshot.meta && initialSnapshot.meta.ui_stale_after_seconds) || 95;
let forceScanAfterSeconds = (initialSnapshot && initialSnapshot.meta && initialSnapshot.meta.ui_force_scan_after_seconds) || 110;
let refreshInFlight = false;
let lastAutoRunScanAt = 0;
let bootstrapPollHandle = null;

function activateTab(tabId, btn){
  const fallbackId = document.getElementById(tabId) ? tabId : 'dashboard';
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.dock-btn').forEach(b=>b.classList.remove('active'));
  const panel=document.getElementById(fallbackId);
  if(panel) panel.classList.add('active');
  const targetBtn = btn || document.querySelector(`.dock-btn[data-tab="${fallbackId}"]`);
  if(targetBtn) targetBtn.classList.add('active');
  window.requestAnimationFrame(()=>{
    window.scrollTo({top:0,behavior:'smooth'});
  });
}
function showTab(tabId, btn){
  activateTab(tabId, btn);
  if(tabId==='futures'){ refreshFuturesPanel(); }
}
window.showTab = showTab;
window.refreshSnapshot = refreshSnapshot;
window.saveCapitalState = saveCapitalState;
function escapeHtml(text){ if(text===null||text===undefined) return ''; return String(text).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;'); }
function formatText(text){ return escapeHtml(text).replace(/\\n/g,'<br>'); }
function formatAge(seconds){ const s=Math.max(0, parseInt(seconds||0,10)||0); if(s<60) return '00:'+String(s).padStart(2,'0'); const m=Math.floor(s/60); const r=s%60; return String(m).padStart(2,'0')+':'+String(r).padStart(2,'0'); }
function badgeInfo(decision, direction){
  const dir = direction || 'CALL';
  if(decision==='ENTRADA_FORTE') return {cls: dir==='PUT'?'put':'call', text:'ENTRADA FORTE'};
  if(decision==='ENTRADA_CAUTELA') return {cls: dir==='PUT'?'put':'call', text:'ENTRADA CAUTELA'};
  if(decision==='OBSERVAR') return {cls:'hold', text:'OBSERVAR'};
  if(decision==='NAO_OPERAR') return {cls:'block', text:'NÃO OPERAR'};
  return {cls:'hold', text: decision || 'AGUARDANDO'};
}
function safeSnapshot(d){
  return {
    signals: Array.isArray(d && d.signals) ? d.signals : [],
    history: Array.isArray(d && d.history) ? d.history : [],
    current_decision: d && d.current_decision ? d.current_decision : {},
    meta: {
      last_scan: d && d.meta && d.meta.last_scan ? d.meta.last_scan : '--',
      scan_count: d && d.meta && typeof d.meta.scan_count !== 'undefined' ? d.meta.scan_count : 0,
      signal_count: d && d.meta && typeof d.meta.signal_count !== 'undefined' ? d.meta.signal_count : 0,
      asset_count: d && d.meta && typeof d.meta.asset_count !== 'undefined' ? d.meta.asset_count : 0,
      scan_in_progress: !!(d && d.meta && d.meta.scan_in_progress),
      last_scan_age_seconds: d && d.meta ? d.meta.last_scan_age_seconds : 0,
      last_scan_trigger: d && d.meta && d.meta.last_scan_trigger ? d.meta.last_scan_trigger : 'loop',
      ui_auto_refresh_seconds: d && d.meta && d.meta.ui_auto_refresh_seconds ? d.meta.ui_auto_refresh_seconds : 20,
      ui_stale_after_seconds: d && d.meta && d.meta.ui_stale_after_seconds ? d.meta.ui_stale_after_seconds : 95,
      ui_force_scan_after_seconds: d && d.meta && d.meta.ui_force_scan_after_seconds ? d.meta.ui_force_scan_after_seconds : 110,
      last_scan_error: d && d.meta && d.meta.last_scan_error ? d.meta.last_scan_error : ''
    },
    learning_stats: d && d.learning_stats ? d.learning_stats : {total:0,wins:0,loss:0,winrate:0},
    best_assets: Array.isArray(d && d.best_assets) ? d.best_assets : [],
    best_hours: Array.isArray(d && d.best_hours) ? d.best_hours : [],
    capital_state: d && d.capital_state ? d.capital_state : {}
  };
}
function updateLiveBadge(meta){
  const el=document.getElementById('liveBadge');
  const status=document.getElementById('top_connection_value');
  if(!el || !meta) return;
  const age=parseInt(meta.last_scan_age_seconds||0,10)||0;
  const stale=parseInt(meta.ui_stale_after_seconds||staleAfterSeconds||95,10)||95;
  if(meta.scan_in_progress){ el.textContent='● ESCANEANDO'; if(status) status.textContent='Ao vivo'; return; }
  if(age>=stale){ el.textContent='● ATRASADO'; if(status) status.textContent='Atenção'; return; }
  el.textContent=age<=5?'● AO VIVO':('● ATUALIZADO ' + formatAge(age));
  if(status) status.textContent='Modo live';
}
function renderDashboardDecision(d){
  const c=document.getElementById('dashboard_decision');
  if(!c) return;
  if(!d || !d.decision){ c.innerHTML=`<div class='empty'>Sem decisão disponível agora.</div>`; return; }
  const b=badgeInfo(d.decision,d.direction);
  const conf=Math.max(2, Math.min(100, parseFloat(d.confidence||0)||0));
  c.innerHTML=`
    <div class='hero-head'>
      <div>
        <div class='asset-title'>${escapeHtml(d.asset || 'MERCADO')}</div>
        <div class='asset-meta'>${escapeHtml((d.provider||'Alpha Hive AI'))} • ${escapeHtml((d.timeframe||'1 minuto'))}</div>
      </div>
      <div class='action-badge ${b.cls}'>✓ ${escapeHtml(b.text)}</div>
    </div>
    <div class='stake-chip'>Stake sugerida: ${escapeHtml(d.stake_suggested != null ? d.stake_suggested : (d.stake || '0.0'))}</div>
    <div class='score-row'>
      <div class='score-tile'><div class='label'>Score</div><div class='value'>${escapeHtml(d.score || '0')}</div></div>
      <div class='score-tile'><div class='label'>Confiança</div><div class='value'>${escapeHtml(d.confidence || 0)}%</div><div class='score-bar'><span style='width:${conf}%'></span></div></div>
    </div>`;
}
function renderDashboardSummary(d){
  const c=document.getElementById('dashboard_summary');
  if(!c) return;
  const points=Array.isArray(d && d.summary_points) ? d.summary_points : [];
  const direction=(d && d.direction) || (points.find(x=>String(x).toLowerCase().includes('direção'))||'--');
  const risk=(points.find(x=>String(x).toLowerCase().includes('risco')))|| ((d && d.behavior_mode)?('Risco: '+d.behavior_mode):'Risco moderado');
  const exec=(points.find(x=>String(x).toLowerCase().includes('execução')))|| ((d && d.validation_mode)?('Execução estatística: '+d.validation_mode):'Execução estatística: modo live');
  c.innerHTML=`
    <div class='detail-line call'><div class='label'>Direção</div><div class='value'>${escapeHtml(String(direction).replace(/^.*?:\\s*/,''))}</div></div>
    <div class='detail-line risk'><div class='label'>Risco</div><div class='value'>${escapeHtml(String(risk).replace(/^.*?:\\s*/,''))}</div></div>
    <div class='detail-line exec'><div class='label'>Execução estatística</div><div class='value'>${escapeHtml(String(exec).replace(/^.*?:\\s*/,''))}</div></div>`;
}
function renderSummaryBlock(title, main, points){
  const safeTitle=escapeHtml(title || 'Resumo operacional');
  const safeMain=escapeHtml(main || 'Sem resumo disponível.');
  const rows=Array.isArray(points) ? points : [];
  const pointsHtml=rows.length ? `<div class='summary-points'>${rows.map(r=>`<div class='summary-point'><span class='dot'>•</span><span>${escapeHtml(r)}</span></div>`).join('')}</div>` : '';
  return `<div class='summary-card'><div class='summary-kicker'>${safeTitle}</div><div class='summary-main'>${safeMain}</div>${pointsHtml}</div>`;
}
function renderAdvancedDetails(reasonText){
  return `<details class='advanced-box'><summary>Detalhes avançados</summary><div class='reason'>${formatText(reasonText || 'Sem detalhes')}</div></details>`;
}
function renderSignals(signals){
  const c=document.getElementById('signals_container'); if(!c) return;
  if(!signals || !signals.length){ c.innerHTML=`<div class='empty'>Nenhum sinal disponível agora.</div>`; return; }
  c.innerHTML = signals.map(s=>{
    const b=s.signal==='PUT' ? 'put' : 'call';
    return `<div class='signal-card'>
      <div class='signal-head'><div class='asset-name'>${escapeHtml(s.asset || 'ATIVO')}</div><div class='badge ${b}'>${escapeHtml((s.signal || '') + ((s.confidence_label ? ' • ' + s.confidence_label : '')))}</div></div>
      <div class='grid-2'>
        <div class='mini-card'><div class='label'>Score</div><div class='value'>${escapeHtml(s.score || '0')}</div></div>
        <div class='mini-card'><div class='label'>Confiança</div><div class='value'>${escapeHtml(s.confidence || '0')}%</div></div>
        <div class='mini-card'><div class='label'>Entrada</div><div class='value'>${escapeHtml(s.entry_time || '--')}</div></div>
        <div class='mini-card'><div class='label'>Regime</div><div class='value'>${escapeHtml(s.regime || '--')}</div></div>
      </div>
      ${renderSummaryBlock(s.summary_title, s.summary_main, s.summary_points)}
      ${renderAdvancedDetails(s.reason_text)}
    </div>`;
  }).join('');
}
function renderDecision(d){
  const c=document.getElementById('decision_container'); if(!c) return;
  if(!d || !d.decision){ c.innerHTML=`<div class='empty'>Sem decisão disponível agora.</div>`; return; }
  const b=badgeInfo(d.decision,d.direction);
  c.innerHTML=`<div class='signal-card'>
    <div class='decision-head'><div class='asset-name'>${escapeHtml(d.asset || 'MERCADO')}</div><div class='badge ${b.cls}'>${escapeHtml(b.text)}</div></div>
    <div class='grid-2'>
      <div class='mini-card'><div class='label'>Score</div><div class='value'>${escapeHtml(d.score || '0')}</div></div>
      <div class='mini-card'><div class='label'>Confiança</div><div class='value'>${escapeHtml(d.confidence || '0')}%</div></div>
      <div class='mini-card'><div class='label'>Análise</div><div class='value'>${escapeHtml(d.analysis_time || '--')}</div></div>
      <div class='mini-card'><div class='label'>Entrada</div><div class='value'>${escapeHtml(d.entry_time || '--')}</div></div>
      <div class='mini-card'><div class='label'>Expiração</div><div class='value'>${escapeHtml(d.expiration || '--')}</div></div>
      <div class='mini-card'><div class='label'>Regime</div><div class='value'>${escapeHtml(d.regime || '--')}</div></div>
    </div>
    ${renderSummaryBlock(d.summary_title, d.summary_main, d.summary_points)}
    <div class='advanced-tip'>A inteligência completa continua ativa; aqui a interface mostra apenas o resumo operacional.</div>
    ${renderAdvancedDetails(d.reason_text)}
  </div>`;
}
function renderHistory(history){
  const c=document.getElementById('history_container'); if(!c) return;
  if(!history || !history.length){ c.innerHTML=`<div class='empty'>Ainda não há histórico salvo.</div>`; return; }
  c.innerHTML = history.map(x=>`<div class='history-card'><div class='asset-title' style='font-size:18px'>${escapeHtml(x.asset || '--')} • ${escapeHtml(x.signal || '--')}</div><div class='advanced-tip'>Análise: ${escapeHtml(x.analysis_time || '--')}<br>Entrada: ${escapeHtml(x.entry_time || '--')}<br>Expiração: ${escapeHtml(x.expiration || '--')}<br>Score: ${escapeHtml(x.score || '0')} • Confiança: ${escapeHtml(x.confidence || '0')}% • Fonte: ${escapeHtml(x.provider || 'Alpha Hive')}</div></div>`).join('');
}
function renderBestAssets(bestAssets){
  const c=document.getElementById('assets_container'); if(!c) return;
  if(!bestAssets || !bestAssets.length){ c.innerHTML=`<div class='empty'>Ainda sem dados suficientes.</div>`; return; }
  c.innerHTML = bestAssets.map(x=>`<div class='rank-card'><div class='asset-title' style='font-size:20px'>${escapeHtml(x.asset)}</div><div class='advanced-tip'>Win rate: <b>${escapeHtml(x.winrate)}%</b><br>Trades: <b>${escapeHtml(x.total)}</b><br>Wins: <b>${escapeHtml(x.wins)}</b></div></div>`).join('');
}
function renderBestHours(bestHours){
  const c=document.getElementById('hours_container'); if(!c) return;
  if(!bestHours || !bestHours.length){ c.innerHTML=`<div class='empty'>Ainda sem dados suficientes.</div>`; return; }
  c.innerHTML = bestHours.map(x=>`<div class='hour-card'><div class='asset-title' style='font-size:20px'>${escapeHtml(x.hour)}h</div><div class='advanced-tip'>Win rate: <b>${escapeHtml(x.winrate)}%</b><br>Trades: <b>${escapeHtml(x.total)}</b><br>Wins: <b>${escapeHtml(x.wins)}</b></div></div>`).join('');
}
function renderStatsPanel(s){
  const c=document.getElementById('stats_panel_container'); if(!c) return;
  c.innerHTML=`<div class='learn-stats'>
      <div class='stat-tile'><div class='label'>Total avaliadas</div><div class='value'>${escapeHtml(s.learning_stats.total || 0)}</div></div>
      <div class='stat-tile positive'><div class='label'>Win rate</div><div class='value'>${escapeHtml(s.learning_stats.winrate || 0)}%</div></div>
      <div class='stat-tile positive'><div class='label'>Wins</div><div class='value'>${escapeHtml(s.learning_stats.wins || 0)}</div></div>
      <div class='stat-tile negative'><div class='label'>Loss</div><div class='value'>${escapeHtml(s.learning_stats.loss || 0)}</div></div>
    </div>
    <div class='performance-row'>
      <div class='trend-card'><div class='panel-head'><h3>Desempenho recente</h3><div class='mini-badge'>IA premium</div></div><div class='sparkline'><svg viewBox='0 0 320 92' preserveAspectRatio='none'><defs><linearGradient id='lineGrad2' x1='0' y1='0' x2='1' y2='0'><stop offset='0%' stop-color='#4ca9ff'/><stop offset='100%' stop-color='#5ff5dc'/></linearGradient></defs><path d='M0 72 C20 68, 30 40, 52 45 S88 77, 110 62 S145 38, 170 46 S205 74, 226 55 S268 29, 320 18' fill='none' stroke='url(#lineGrad2)' stroke-width='3' stroke-linecap='round'/><path d='M0 92 L0 72 C20 68, 30 40, 52 45 S88 77, 110 62 S145 38, 170 46 S205 74, 226 55 S268 29, 320 18 L320 92 Z' fill='rgba(95,245,220,.10)'/></svg></div></div>
      <div class='performance-card'><div class='panel-head'><h3>Resumo</h3><div class='mini-badge'>Live</div></div><div class='advanced-tip'>Scans: <b>${escapeHtml(s.meta.scan_count)}</b><br>Sinais: <b>${escapeHtml(s.meta.signal_count)}</b><br>Ativos: <b>${escapeHtml(s.meta.asset_count)}</b><br>Último scan: <b>${escapeHtml(s.meta.last_scan)}</b></div></div>
    </div>`;
}
async function getJSON(url){
  const resp = await fetch(url, {cache:'no-store'});
  return await resp.json();
}
async function postJSON(url, payload){
  const resp = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload || {})});
  return await resp.json();
}
function renderFuturesPlan(plan, execution){
  const c=document.getElementById('f_plan_container'); if(!c) return;
  if(!plan){ c.innerHTML="<div class='empty'>Sem plano futures no momento.</div>"; return; }
  const tps = Array.isArray(plan.take_profits) ? plan.take_profits : [];
  const rr = plan.risk_reward != null ? plan.risk_reward : '--';
  const execNote = execution && execution.note ? execution.note : 'Sem execução recente.';
  c.innerHTML=`<div class='signal-card'>
    <div class='signal-head'><div class='asset-name'>${escapeHtml(plan.asset || 'ATIVO')}</div><div class='badge ${String(plan.direction||'').toUpperCase()==='SHORT'?'put':'call'}'>${escapeHtml(plan.direction || plan.status || 'READY')}</div></div>
    <div class='grid-2'>
      <div class='mini-card'><div class='label'>Entry</div><div class='value'>${escapeHtml(plan.entry || '--')}</div></div>
      <div class='mini-card'><div class='label'>Stop</div><div class='value'>${escapeHtml(plan.stop_loss || '--')}</div></div>
      <div class='mini-card'><div class='label'>RR</div><div class='value'>${escapeHtml(rr)}</div></div>
      <div class='mini-card'><div class='label'>Lev.</div><div class='value'>${escapeHtml(plan.leverage || '--')}x</div></div>
      <div class='mini-card'><div class='label'>Confiança</div><div class='value'>${escapeHtml(plan.confidence || '--')}%</div></div>
      <div class='mini-card'><div class='label'>Qty</div><div class='value'>${escapeHtml(plan.quantity || '--')}</div></div>
    </div>
    ${tps.length ? `<div class='advanced-tip' style='margin-top:12px'>${tps.map(tp=>`${escapeHtml(tp.label)}: <b>${escapeHtml(tp.price)}</b> (${escapeHtml(tp.size_pct)}%)`).join('<br>')}</div>` : ''}
    <div class='advanced-tip' style='margin-top:12px'>${escapeHtml(execNote)}</div>
  </div>`;
}
function renderFuturesAccount(data){
  const c=document.getElementById('f_account_container'); if(!c) return;
  if(!data || !data.ok){ c.innerHTML=`Sem conexão ativa com a Binance Futures.`; return; }
  const s=data.summary || {};
  c.innerHTML=`Saldo USDT: <b>${escapeHtml((s.total_wallet_balance ?? 0).toFixed ? s.total_wallet_balance.toFixed(2) : s.total_wallet_balance)}</b><br>Disponível: <b>${escapeHtml((s.available_balance ?? 0).toFixed ? s.available_balance.toFixed(2) : s.available_balance)}</b><br>Unrealized PnL: <b>${escapeHtml((s.total_unrealized_profit ?? 0).toFixed ? s.total_unrealized_profit.toFixed(2) : s.total_unrealized_profit)}</b>`;
}
function renderFuturesPositions(data){
  const c=document.getElementById('f_positions_container'); if(!c) return;
  const rows=(data && data.positions) || [];
  if(!rows.length){ c.innerHTML="<div class='advanced-tip'>Sem posições abertas.</div>"; return; }
  c.innerHTML=rows.map(p=>`<div class='history-card'><b>${escapeHtml(p.symbol)}</b> • ${escapeHtml(p.side)}<br>Entry: <b>${escapeHtml(p.entry_price)}</b> • Mark: <b>${escapeHtml(p.mark_price)}</b><br>PnL: <b>${escapeHtml(p.unrealized_pnl)}</b> • Liq: <b>${escapeHtml(p.liquidation_price)}</b> • Lev: <b>${escapeHtml(p.leverage)}x</b></div>`).join('');
}
function renderFuturesOrders(data){
  const c=document.getElementById('f_orders_container'); if(!c) return;
  const rows=(data && data.orders) || [];
  if(!rows.length){ c.innerHTML="<div class='advanced-tip'>Sem ordens abertas.</div>"; return; }
  c.innerHTML=rows.slice(0,8).map(o=>`<div class='history-card'><b>${escapeHtml(o.symbol)}</b> • ${escapeHtml(o.side)} • ${escapeHtml(o.type)}<br>Status: <b>${escapeHtml(o.status)}</b> • Qty: <b>${escapeHtml(o.orig_qty)}</b><br>Price: <b>${escapeHtml(o.price)}</b> • Stop: <b>${escapeHtml(o.stop_price)}</b></div>`).join('');
}
function renderFuturesBot(bot){
  const s=document.getElementById('f_bot_status');
  const l=document.getElementById('f_bot_logs');
  if(!s || !l) return;
  if(!bot){ s.textContent='Sem status do bot.'; l.textContent=''; return; }
  s.innerHTML=`Running: <b>${escapeHtml(bot.running ? 'SIM' : 'NÃO')}</b><br>Symbol: <b>${escapeHtml(bot.symbol || '--')}</b> • Timeframe: <b>${escapeHtml(bot.timeframe || '--')}</b><br>Mode: <b>${escapeHtml(bot.execution_mode || '--')}</b> • Último run: <b>${escapeHtml(bot.last_run_at || '--')}</b>${bot.last_error ? `<br>Erro: <b>${escapeHtml(bot.last_error)}</b>` : ''}`;
  const logs = Array.isArray(bot.logs) ? bot.logs.slice(-8).reverse() : [];
  l.textContent = logs.map(x=>`[${x.level}] ${x.ts} - ${x.message}`).join('
');
}
async function refreshFuturesPanel(){
  try{
    const status = await getJSON('/futures/status');
    const conn=status.connection || {};
    const c=document.getElementById('f_connection_status');
    if(c){ c.innerHTML=`Conexão: <b>${conn.connected ? 'ATIVA' : 'INATIVA'}</b> • Origem: <b>${escapeHtml(conn.source || 'none')}</b> • Testnet: <b>${conn.testnet ? 'SIM' : 'NÃO'}</b> ${conn.api_key_masked ? '• Key: <b>'+escapeHtml(conn.api_key_masked)+'</b>' : ''}`; }
    renderFuturesBot(status.bot || {});
    const last = status.bot && status.bot.last_result ? status.bot.last_result : {};
    renderFuturesPlan(last.plan || null, last.execution || null);
    if(conn.connected){
      const symbol=(document.getElementById('f_symbol') && document.getElementById('f_symbol').value) || 'BTCUSDT';
      const [account, positions, orders] = await Promise.all([
        getJSON('/futures/account'),
        getJSON('/futures/positions'),
        getJSON('/futures/orders?symbol='+encodeURIComponent(symbol))
      ]);
      renderFuturesAccount(account); renderFuturesPositions(positions); renderFuturesOrders(orders);
    } else {
      renderFuturesAccount(null); renderFuturesPositions({positions:[]}); renderFuturesOrders({orders:[]});
    }
  }catch(e){ console.error('refresh futures error', e); }
}
async function futuresConnect(){
  const api_key=(document.getElementById('f_api_key').value || '').trim();
  const api_secret=(document.getElementById('f_api_secret').value || '').trim();
  const testnet=(document.getElementById('f_testnet').value || '1');
  const out=document.getElementById('f_connection_status');
  if(out) out.textContent='Conectando...';
  try{
    const data = await postJSON('/futures/connect', {api_key, api_secret, testnet});
    if(out) out.textContent = data.ok ? 'Conectado com sucesso.' : 'Falha ao conectar.';
    await refreshFuturesPanel();
  }catch(e){ if(out) out.textContent='Erro ao conectar.'; }
}
async function futuresDisconnect(){
  await postJSON('/futures/disconnect', {});
  await refreshFuturesPanel();
}
async function futuresAnalyze(){
  const symbol=(document.getElementById('f_symbol').value || 'BTCUSDT').trim().toUpperCase();
  const timeframe=(document.getElementById('f_timeframe').value || '1m').trim();
  const execution_mode=(document.getElementById('f_execution_mode').value || 'paper').trim();
  const data = await getJSON(`/futures/analyze?asset=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&execution_mode=${encodeURIComponent(execution_mode)}&leverage=${encodeURIComponent(document.getElementById('f_leverage').value || '3')}&risk_per_trade_pct=${encodeURIComponent(document.getElementById('f_risk_pct').value || '0.6')}&max_trades_per_day=${encodeURIComponent(document.getElementById('f_max_trades').value || '3')}`);
  renderFuturesPlan(data, null);
}
async function futuresStartBot(){
  const payload={
    symbol:(document.getElementById('f_symbol').value || 'BTCUSDT').trim().toUpperCase(),
    timeframe:(document.getElementById('f_timeframe').value || '1m').trim(),
    execution_mode:(document.getElementById('f_execution_mode').value || 'paper').trim(),
    leverage:parseFloat(document.getElementById('f_leverage').value || 3),
    risk_per_trade_pct:parseFloat(document.getElementById('f_risk_pct').value || 0.6),
    max_trades_per_day:parseInt(document.getElementById('f_max_trades').value || 3,10) || 3,
    poll_seconds:parseInt(document.getElementById('f_poll_seconds').value || 45,10) || 45
  };
  await postJSON('/futures/bot/start', payload);
  await refreshFuturesPanel();
}
async function futuresStopBot(){
  await postJSON('/futures/bot/stop', {});
  await refreshFuturesPanel();
}
window.futuresConnect=futuresConnect;
window.futuresDisconnect=futuresDisconnect;
window.futuresAnalyze=futuresAnalyze;
window.futuresStartBot=futuresStartBot;
window.futuresStopBot=futuresStopBot;

function fillCapitalForm(cap){
  const ids=['capital_current','capital_peak','daily_pnl','streak','daily_target_pct','daily_stop_pct'];
  ids.forEach(id=>{const el=document.getElementById(id); if(el) el.value = cap[id] ?? (id==='daily_target_pct'?2.0:id==='daily_stop_pct'?3.0:0);});
}
function applySnapshot(d){
  const s=safeSnapshot(d);
  window.__lastSnapshot = s;
  autoRefreshSeconds=parseInt((s.meta && s.meta.ui_auto_refresh_seconds) || autoRefreshSeconds || 20,10)||20;
  staleAfterSeconds=parseInt((s.meta && s.meta.ui_stale_after_seconds) || staleAfterSeconds || 95,10)||95;
  forceScanAfterSeconds=parseInt((s.meta && s.meta.ui_force_scan_after_seconds) || forceScanAfterSeconds || 110,10)||110;
  document.getElementById('top_asset_value').textContent=(s.current_decision && s.current_decision.asset) || (s.signals[0] && s.signals[0].asset) || 'Mercado';
  document.getElementById('top_regime_value').textContent=(s.current_decision && s.current_decision.regime) || (s.signals[0] && s.signals[0].regime) || 'Misto';
  document.getElementById('dash_analysis').textContent=(s.current_decision && s.current_decision.analysis_time) || '--:--';
  document.getElementById('dash_entry').textContent=(s.current_decision && s.current_decision.entry_time) || '--:--';
  document.getElementById('dash_expiration').textContent=(s.current_decision && s.current_decision.expiration) || '--:--';
  document.getElementById('dash_regime').textContent=(s.current_decision && s.current_decision.regime) || '--';
  document.getElementById('scan_age_big').textContent=formatAge((s.meta && s.meta.last_scan_age_seconds) || 0);
  document.getElementById('scan_sub').textContent=s.meta.scan_in_progress ? 'Escaneando padrões de alta probabilidade...' : ('Último scan em ' + (s.meta.last_scan || '--'));
  document.getElementById('dash_health_badge').textContent=((s.current_decision && s.current_decision.decision==='NAO_OPERAR') ? 'Modo defensivo' : 'Nível saudável');
  document.getElementById('stats_total').textContent=s.learning_stats.total || 0;
  document.getElementById('stats_wr').textContent=(s.learning_stats.winrate || 0) + '%';
  document.getElementById('stats_wins').textContent=s.learning_stats.wins || 0;
  document.getElementById('stats_loss').textContent=s.learning_stats.loss || 0;
  document.getElementById('side_scans').textContent=s.meta.scan_count || 0;
  document.getElementById('side_signals').textContent=s.meta.signal_count || 0;
  document.getElementById('side_assets').textContent=s.meta.asset_count || 0;
  document.getElementById('side_update').textContent=s.meta.last_scan || '--';
  document.getElementById('wr_ring_text').textContent=(s.learning_stats.winrate || 0)+'%';
  const win=Math.max(0, Math.min(100, parseFloat(s.learning_stats.winrate || 0) || 0));
  const ring=document.getElementById('wr_ring');
  if(ring){ ring.style.background=`conic-gradient(var(--teal) 0deg, var(--cyan) ${win*3.6}deg, rgba(255,255,255,.08) ${win*3.6}deg 360deg)`; }
  document.getElementById('trend_badge').textContent=win>=58?'Tendência positiva':(win>=52?'Tendência estável':'Tendência defensiva');
  renderDashboardDecision(s.current_decision || {});
  renderDashboardSummary(s.current_decision || {});
  renderSignals(s.signals);
  renderDecision(s.current_decision || {});
  renderHistory(s.history);
  renderBestAssets(s.best_assets);
  renderBestHours(s.best_hours);
  renderStatsPanel(s);
  fillCapitalForm(s.capital_state || {});
  updateLiveBadge(s.meta || {});
  if(document.getElementById('futures') && document.getElementById('futures').classList.contains('active')){ refreshFuturesPanel(); }
  startAutoRefresh();
}
async function maybeTriggerScan(meta){
  const age = parseInt((meta && meta.last_scan_age_seconds) || 0, 10) || 0;
  const count = parseInt((meta && meta.scan_count) || 0, 10) || 0;
  const missingBootstrap = !meta || !meta.last_scan || meta.last_scan === '--' || count <= 0;
  if(!missingBootstrap && age < (parseInt((meta && meta.ui_force_scan_after_seconds) || forceScanAfterSeconds || 110, 10) || 110)) return;
  const now = Date.now();
  if(now - lastAutoRunScanAt < (missingBootstrap ? 5000 : 45000)) return;
  lastAutoRunScanAt = now;
  try{ await fetch('/run-scan', {cache:'no-store'}); }catch(e){ console.error('run-scan warning', e); }
}
async function refreshSnapshot(silent){
  if(refreshInFlight) return;
  refreshInFlight = true;
  const btn = document.getElementById('refreshBtn');
  if(btn && !silent){ btn.disabled = true; btn.textContent = 'Atualizando...'; }
  const controller = new AbortController();
  const timeout = setTimeout(()=>controller.abort(), 12000);
  try{
    const resp = await fetch('/snapshot', {cache:'no-store', signal:controller.signal});
    const data = await resp.json();
    applySnapshot(data);
    if(document.querySelector('.dock-btn.active') && document.querySelector('.dock-btn.active').dataset.tab === 'futures'){
      refreshFuturesPanel();
    }
    await maybeTriggerScan(data.meta || {});
  }catch(e){ console.error('snapshot refresh error', e); }
  finally{
    clearTimeout(timeout);
    refreshInFlight = false;
    if(btn && !silent){ setTimeout(()=>{ btn.disabled=false; btn.textContent='↻ Atualizar agora'; }, 600); }
  }
}
function startAutoRefresh(){
  if(autoRefreshHandle) clearInterval(autoRefreshHandle);
  autoRefreshHandle = setInterval(()=>{ if(document.hidden) return; refreshSnapshot(true); }, Math.max(8, autoRefreshSeconds) * 1000);
}
function startBootstrapPolling(){
  if(bootstrapPollHandle) clearInterval(bootstrapPollHandle);
  const current = safeSnapshot(window.__lastSnapshot || initialSnapshot || null);
  if((current.meta && current.meta.scan_count) > 0 && (current.signals.length > 0 || (current.current_decision && current.current_decision.asset && current.current_decision.asset !== 'MERCADO'))){
    return;
  }
  bootstrapPollHandle = setInterval(async ()=>{
    const latest = safeSnapshot(window.__lastSnapshot || initialSnapshot || null);
    if((latest.meta && latest.meta.scan_count) > 0 && (latest.signals.length > 0 || (latest.current_decision && latest.current_decision.asset && latest.current_decision.asset !== 'MERCADO'))){
      clearInterval(bootstrapPollHandle);
      bootstrapPollHandle = null;
      return;
    }
    await refreshSnapshot(true);
  }, 2500);
}
async function saveCapitalState(){
  const btn=document.getElementById('saveCapitalBtn');
  const status=document.getElementById('capital_status');
  if(!btn || !status) return;
  btn.disabled=true; status.textContent='Salvando...';
  const payload={
    capital_current: parseFloat(document.getElementById('capital_current').value || 0),
    capital_peak: parseFloat(document.getElementById('capital_peak').value || 0),
    daily_pnl: parseFloat(document.getElementById('daily_pnl').value || 0),
    streak: parseInt(document.getElementById('streak').value || 0, 10) || 0,
    daily_target_pct: parseFloat(document.getElementById('daily_target_pct').value || 2.0),
    daily_stop_pct: parseFloat(document.getElementById('daily_stop_pct').value || 3.0)
  };
  try{
    await fetch('/capital-state', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    status.textContent='Capital salvo com sucesso.';
    setTimeout(()=>status.textContent='', 2200);
  }catch(e){ status.textContent='Erro ao salvar capital.'; }
  setTimeout(()=>{ btn.disabled=false; },800);
}
document.addEventListener('DOMContentLoaded', function(){
  const defaultTabBtn = document.querySelector('.dock-btn[data-tab="dashboard"]');
  activateTab('dashboard', defaultTabBtn);
  document.addEventListener('click', function(ev){
    const tabBtn = ev.target.closest('.dock-btn[data-tab]');
    if(tabBtn){
      ev.preventDefault();
      activateTab(tabBtn.dataset.tab, tabBtn);
      return;
    }
  });
  try{ applySnapshot(initialSnapshot); }catch(e){ console.error('initial snapshot error', e); applySnapshot(null); }
  startAutoRefresh();
  startBootstrapPolling();
  setTimeout(()=>refreshSnapshot(true), 250);
  document.addEventListener('visibilitychange', function(){ if(!document.hidden){ refreshSnapshot(true); } });
});
</script>
</body>
</html>
"""


@app.route("/")
def home():
    # Faz o primeiro bootstrap de forma síncrona para evitar tela vazia na carga inicial.
    ensure_bootstrap_snapshot(force=True)
    ensure_scanner_started()
    return render_template_string(HTML_PAGE, snapshot_json=safe_dumps(get_snapshot(light=True)))


import time

START_TIME = time.time()

@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "service": "alpha-hive",
        "alive": True,
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }, 200


@app.route("/edge-report", methods=["GET"])
def edge_report_get():
    return jsonify(to_jsonable(edge_audit.compute_report()))


@app.route("/capital-state", methods=["GET"])
def capital_state_get():
    ensure_scanner_started()
    capital_auto_tracker.update()
    return jsonify(to_jsonable(load_capital_state()))


@app.route("/capital-state", methods=["POST"])
def capital_state_post():
    ensure_scanner_started()
    payload = request.get_json(silent=True) or {}
    save_capital_state(payload)
    capital_auto_tracker.update()
    return jsonify(to_jsonable(load_capital_state()))


@app.route("/snapshot")
def snapshot():
    ensure_bootstrap_snapshot(force=False)
    ensure_scanner_started()
    try:
        signals, history, current_decision, meta = ensure_bootstrap_snapshot(force=False)
        if _snapshot_is_empty(signals, history, current_decision, meta) and not scan_in_progress:
            signals, history, current_decision, meta = ensure_bootstrap_snapshot(force=True)
        return jsonify(to_jsonable(get_snapshot(light=True)))
    except Exception as e:
        print(f"snapshot route warning: {e}", flush=True)
        signals, history, current_decision, meta = load_state()
        return jsonify(to_jsonable({
            "signals": signals,
            "history": history[:20],
            "current_decision": current_decision,
            "meta": {
                "last_scan": (meta or {}).get("last_scan", "--"),
                "scan_count": (meta or {}).get("scan_count", 0),
                "signal_count": len(signals),
                "asset_count": len(ASSETS),
            },
            "learning_stats": {"total": 0, "wins": 0, "loss": 0, "winrate": 0.0},
            "best_assets": [],
            "best_hours": [],
            "capital_state": load_capital_state(),
        }))


@app.route("/ping")
def ping():
    return {
        "status": "ok",
        "backend": state_store.backend_name,
        "scanner_in_progress": bool(scan_in_progress),
        "scan_count": int(scan_count or 0),
        "last_scan_age_seconds": 0 if not last_scan_finished_ts else max(0, int(time.time() - last_scan_finished_ts)),
    }


@app.route("/run-scan", methods=["GET", "POST"])
def run_scan_route():
    ensure_scanner_started()
    if not SCAN_ROUTE_ENABLED:
        return jsonify({"ok": False, "error": "scan_route_disabled"}), 403
    if SCAN_TRIGGER_TOKEN:
        provided = request.args.get("token") or request.headers.get("X-Scan-Token") or ""
        if provided != SCAN_TRIGGER_TOKEN:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
    if scan_in_progress:
        return jsonify({"ok": True, "ran": False, "reason": "scan_already_running", "scan_count": int(scan_count or 0)}), 202
    result = run_scan_once("manual")
    code = 200 if result.get("ok") else 500
    result["backend"] = state_store.backend_name
    result["last_scan_age_seconds"] = 0 if not last_scan_finished_ts else max(0, int(time.time() - last_scan_finished_ts))
    return jsonify(to_jsonable(result)), code


@app.route("/edge-guard", methods=["GET"])
def edge_guard_report():
    return jsonify(to_jsonable(edge_guard.evaluate(asset="GLOBAL", regime="global", strategy_name="global", analysis_time=None, proposed_decision="OBSERVAR", proposed_score=0.0, proposed_confidence=50)))


@app.route("/specialists", methods=["GET"])
def specialists_report():
    return jsonify(to_jsonable({
        "leaders": specialist_reputation.snapshot(limit=25),
        "current_council": read_json(CURRENT_DECISION_FILE, {}).get("trader_council", {}),
    }))

@app.route("/memory-integrity", methods=["GET"])
def memory_integrity():
    ensure_scanner_started()
    return jsonify(to_jsonable(memory_integrity_status()))


@app.route("/storage-health", methods=["GET"])
def storage_health():
    ensure_scanner_started()
    force = str(request.args.get('force', '')).lower() in ('1','true','yes')
    if force:
        report = storage_governance.maybe_run_maintenance(scan_count=scan_count, force=True)
    else:
        report = storage_governance.collect_report()
    return jsonify(to_jsonable(report))


@app.route("/futures/analyze", methods=["GET"])
def futures_analyze_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    sync_futures_credentials_from_vault()
    asset = str(request.args.get("asset") or "").upper().strip() or None
    execution_mode = str(request.args.get("execution_mode") or "paper").lower().strip()
    timeframe = str(request.args.get("timeframe") or "1m").strip().lower()
    strategy_name = str(request.args.get("strategy") or "futures_confluence").strip()
    leverage = request.args.get("leverage")
    risk_per_trade_pct = request.args.get("risk_per_trade_pct")
    max_trades_per_day = request.args.get("max_trades_per_day")
    market = scanner.scan_assets(timeframe=timeframe, assets=[asset] if asset else None, outputsize=120)
    result = futures_module.analyze_market(
        market,
        capital_state=load_capital_state(),
        asset=asset,
        execution_mode=execution_mode,
        timeframe=timeframe,
        strategy_name=strategy_name,
        leverage_override=leverage,
        risk_pct_override=(float(risk_per_trade_pct) / 100.0) if risk_per_trade_pct not in (None, "") else None,
        max_trades_per_day=max_trades_per_day,
    )
    return jsonify(to_jsonable(result))


@app.route("/futures/execute", methods=["POST"])
def futures_execute_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    sync_futures_credentials_from_vault()
    payload = request.get_json(silent=True) or {}
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else None
    asset = str(payload.get("asset") or "").upper().strip() or None
    execution_mode = str(payload.get("execution_mode") or "paper").lower().strip()
    timeframe = str(payload.get("timeframe") or "1m").strip().lower()
    strategy_name = str(payload.get("strategy") or "futures_confluence").strip()
    leverage = payload.get("leverage")
    risk_per_trade_pct = payload.get("risk_per_trade_pct")
    max_trades_per_day = payload.get("max_trades_per_day")
    live = execution_mode == "live"
    if not plan:
        market = scanner.scan_assets(timeframe=timeframe, assets=[asset] if asset else None, outputsize=120)
        plan = futures_module.analyze_market(
            market,
            capital_state=load_capital_state(),
            asset=asset,
            execution_mode=execution_mode,
            timeframe=timeframe,
            strategy_name=strategy_name,
            leverage_override=leverage,
            risk_pct_override=(float(risk_per_trade_pct) / 100.0) if risk_per_trade_pct not in (None, "") else None,
            max_trades_per_day=max_trades_per_day,
        )
    execution = futures_module.execute_signal(plan, live=live)
    return jsonify(to_jsonable({"ok": True, "plan": plan, "execution": execution, "connection": binance_vault.status()}))


@app.route("/futures/close-report", methods=["POST"])
def futures_close_report_route():
    ensure_scanner_started()
    payload = request.get_json(silent=True) or {}
    trade = self_optimization_engine.register_futures_close(payload)
    return jsonify(to_jsonable({
        "ok": trade is not None,
        "registered_trade": trade,
        "self_optimization": self_optimization_engine.summary() if self_optimization_engine else {},
    }))


@app.route("/futures/status", methods=["GET"])
def futures_status_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return jsonify(to_jsonable({"ok": False, "connection": {"connected": False, "source": "none", "testnet": False}, "bot": {"running": False}, "self_optimization": {}, "details": futures_feature_status()})), 200
    sync_futures_credentials_from_vault()
    return jsonify(to_jsonable({
        "ok": True,
        "connection": binance_vault.status(),
        "bot": futures_bot_service.status(),
        "self_optimization": self_optimization_engine.summary(),
    }))


@app.route("/futures/connect", methods=["POST"])
def futures_connect_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    payload = request.get_json(silent=True) or {}
    api_key = str(payload.get("api_key") or "").strip()
    api_secret = str(payload.get("api_secret") or "").strip()
    testnet = str(payload.get("testnet") or "1").strip().lower() in ("1", "true", "yes")
    if api_key and api_secret:
        binance_vault.set_credentials(api_key, api_secret, testnet=testnet)
    sync_futures_credentials_from_vault()
    ping = binance_broker.ping()
    return jsonify(to_jsonable({
        "ok": bool(ping.get("ok")),
        "connection": binance_vault.status(),
        "exchange": ping,
        "note": "Credenciais salvas apenas em memória desta instância. Para persistir no Render, use env vars.",
    })), (200 if ping.get("ok") else 400)


@app.route("/futures/disconnect", methods=["POST"])
def futures_disconnect_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    binance_vault.clear_credentials()
    sync_futures_credentials_from_vault()
    return jsonify(to_jsonable({"ok": True, "connection": binance_vault.status()}))


@app.route("/futures/account", methods=["GET"])
def futures_account_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    sync_futures_credentials_from_vault()
    return jsonify(to_jsonable(binance_broker.account_overview()))


@app.route("/futures/positions", methods=["GET"])
def futures_positions_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    sync_futures_credentials_from_vault()
    return jsonify(to_jsonable(binance_broker.positions()))


@app.route("/futures/orders", methods=["GET"])
def futures_orders_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    sync_futures_credentials_from_vault()
    symbol = str(request.args.get("symbol") or "").upper().strip() or None
    return jsonify(to_jsonable(binance_broker.open_orders(symbol=symbol)))


@app.route("/futures/bot/start", methods=["POST"])
def futures_bot_start_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    sync_futures_credentials_from_vault()
    payload = request.get_json(silent=True) or {}
    config = {
        "symbol": str(payload.get("symbol") or "BTCUSDT").upper().strip(),
        "timeframe": str(payload.get("timeframe") or "1m").strip().lower(),
        "execution_mode": str(payload.get("execution_mode") or "paper").strip().lower(),
        "strategy": str(payload.get("strategy") or "futures_confluence").strip(),
        "risk_per_trade_pct": float(payload.get("risk_per_trade_pct") or 0.6),
        "leverage": int(float(payload.get("leverage") or 3)),
        "max_trades_per_day": int(float(payload.get("max_trades_per_day") or 3)),
        "poll_seconds": int(float(payload.get("poll_seconds") or 45)),
    }
    status = futures_bot_service.start(config=config)
    return jsonify(to_jsonable({"ok": True, "bot": status, "connection": binance_vault.status()}))


@app.route("/futures/bot/stop", methods=["POST"])
def futures_bot_stop_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return _futures_disabled_response()
    status = futures_bot_service.stop()
    return jsonify(to_jsonable({"ok": True, "bot": status}))


@app.route("/futures/bot/status", methods=["GET"])
def futures_bot_status_route():
    ensure_scanner_started()
    if not futures_feature_status()["available"]:
        return jsonify(to_jsonable({"ok": False, "bot": {"running": False}, "details": futures_feature_status()})), 200
    return jsonify(to_jsonable({"ok": True, "bot": futures_bot_service.status()}))


if __name__ == "__main__":
    ensure_scanner_started()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)