import json
import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request
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
        "payout": float(decision.get("payout", DEFAULT_PAYOUT) or DEFAULT_PAYOUT),
        "provider": decision.get("provider", "auto"),
        "provider_trust_score": decision.get("provider_trust_score", 1.0),
        "provider_is_fallback": decision.get("provider_is_fallback", False),
        "market_type": decision.get("market_type", "unknown"),
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
        "provider": signal.get("provider", "auto"),
        "provider_trust_score": signal.get("provider_trust_score", 1.0),
        "provider_is_fallback": signal.get("provider_is_fallback", False),
        "market_type": signal.get("market_type", "unknown"),
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




@app.route("/")
def home():
    ensure_scanner_started()
    return render_template("index.html", snapshot_json=safe_dumps(get_snapshot(light=True)))


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
    ensure_scanner_started()
    try:
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


if __name__ == "__main__":
    ensure_scanner_started()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)