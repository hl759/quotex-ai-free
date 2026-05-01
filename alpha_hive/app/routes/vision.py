from __future__ import annotations
import base64, hashlib, json, os, re, time, uuid
from datetime import datetime, timezone, timedelta

import requests
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.storage.state_store import get_state_store

bp = Blueprint("vision", __name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "").strip()
DATABASE_URL   = os.getenv("DATABASE_URL", "").strip()

VISION_COLLECTION = "vision_analyses_v1"

# ── DB ────────────────────────────────────────────────────────────────────────

def _db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=5)

def _init_db():
    if not DATABASE_URL:
        return
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vision_analyses (
                        id SERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        image_hash TEXT,
                        timeframe TEXT,
                        direction TEXT,
                        confidence INT,
                        regime TEXT,
                        setup TEXT,
                        risk TEXT,
                        decision TEXT,
                        summary TEXT,
                        reasons JSONB,
                        result TEXT DEFAULT 'pending'
                    )
                """)
            conn.commit()
    except Exception as e:
        print(f"[vision] db init error: {e}")

_init_db()

# ── STATS / CONTEXT ───────────────────────────────────────────────────────────

def _get_stats():
    if not DATABASE_URL:
        return None
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                        ROUND(AVG(confidence)) as avg_confidence
                    FROM vision_analyses WHERE result IN ('win','loss')
                """)
                overall = cur.fetchone()
                cur.execute("""
                    SELECT regime, COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins
                    FROM vision_analyses WHERE result IN ('win','loss') AND regime IS NOT NULL
                    GROUP BY regime ORDER BY total DESC LIMIT 10
                """)
                by_regime = cur.fetchall()
                cur.execute("""
                    SELECT setup, COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins
                    FROM vision_analyses WHERE result IN ('win','loss') AND setup IS NOT NULL
                    GROUP BY setup ORDER BY total DESC
                """)
                by_setup = cur.fetchall()
                cur.execute("""
                    SELECT direction, COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins
                    FROM vision_analyses WHERE result IN ('win','loss') AND direction IS NOT NULL
                    GROUP BY direction
                """)
                by_direction = cur.fetchall()
                cur.execute("""
                    SELECT direction, regime, setup, confidence, result, summary
                    FROM vision_analyses WHERE result IN ('win','loss')
                    ORDER BY created_at DESC LIMIT 10
                """)
                recent = cur.fetchall()
                return {
                    "overall": dict(overall) if overall else {},
                    "by_regime": [dict(r) for r in by_regime],
                    "by_setup": [dict(r) for r in by_setup],
                    "by_direction": [dict(r) for r in by_direction],
                    "recent": [dict(r) for r in recent],
                }
    except Exception as e:
        print(f"[vision] stats error: {e}")
        return None

def _build_context(stats, timeframe):
    if not stats or not stats["overall"].get("total"):
        return ""
    o = stats["overall"]
    total = int(o.get("total") or 0)
    if total == 0:
        return ""
    wins = int(o.get("wins") or 0)
    losses = int(o.get("losses") or 0)
    wr = round(wins / total * 100) if total > 0 else 0
    lines = [f"\n\n=== MEMÓRIA COLETIVA DE {min(total,200)} OPERAÇÕES ==="]
    lines.append(f"Win rate geral: {wr}% ({wins}W/{losses}L de {total} operações)")
    if stats["by_regime"]:
        lines.append("\nPerformance por regime:")
        for r in stats["by_regime"]:
            t = int(r["total"] or 0); w = int(r["wins"] or 0)
            pct = round(w/t*100) if t > 0 else 0
            flag = "✅" if pct >= 60 else "⚠️" if pct >= 45 else "❌"
            lines.append(f"  {flag} {r['regime']}: {pct}% win ({t} ops)")
    if stats["by_setup"]:
        lines.append("\nPerformance por setup:")
        for r in stats["by_setup"]:
            t = int(r["total"] or 0); w = int(r["wins"] or 0)
            pct = round(w/t*100) if t > 0 else 0
            flag = "✅" if pct >= 60 else "⚠️" if pct >= 45 else "❌"
            lines.append(f"  {flag} {r['setup']}: {pct}% win ({t} ops)")
    if stats["by_direction"]:
        lines.append("\nPerformance por direção:")
        for r in stats["by_direction"]:
            t = int(r["total"] or 0); w = int(r["wins"] or 0)
            pct = round(w/t*100) if t > 0 else 0
            lines.append(f"  {'📈' if r['direction']=='CALL' else '📉'} {r['direction']}: {pct}% win ({t} ops)")
    if stats["recent"]:
        lines.append("\nÚltimas operações:")
        for r in stats["recent"]:
            icon = "✅" if r["result"] == "win" else "❌"
            lines.append(f"  {icon} {r['direction']} | {r['regime']} | {r['setup']} | {r['confidence']}% conf")
    lines.append("\nUSE ESSES DADOS para calibrar sua análise. Regime/setup com win rate baixo = mais conservador. Win rate alto = pode ser mais agressivo.")
    lines.append("=== FIM DA MEMÓRIA ===")
    return "\n".join(lines)

# ── PARSING ───────────────────────────────────────────────────────────────────

def _parse(raw):
    if not raw or not raw.strip():
        raise ValueError("Resposta vazia do modelo")
    raw = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
    raw = re.sub(r"```$", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"Nenhum JSON na resposta: {raw[:120]}")
    return json.loads(m.group(0))

# ── PROVIDERS ─────────────────────────────────────────────────────────────────

def _groq(image_data, mime, prompt):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json={
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                {"type": "text", "text": prompt}
            ]}],
            "max_tokens": 700,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        timeout=30
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return _parse(content)

def _gemini(image_data, mime, prompt):
    for model in ["gemini-1.5-pro", "gemini-1.5-flash"]:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                json={"contents": [{"parts": [
                    {"inline_data": {"mime_type": mime, "data": image_data}},
                    {"text": prompt}
                ]}], "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 700,
                    "responseMimeType": "application/json",
                }},
                params={"key": GEMINI_API_KEY}, timeout=45
            )
            if r.status_code in (429, 404): continue
            r.raise_for_status()
            d = r.json()
            if not d.get("candidates"): continue
            text = d["candidates"][0]["content"]["parts"][0].get("text", "")
            return _parse(text)
        except Exception:
            continue
    return None

# ── SAVE ──────────────────────────────────────────────────────────────────────

def _save(image_hash, timeframe, result_data):
    if not DATABASE_URL:
        return None
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO vision_analyses
                        (image_hash, timeframe, direction, confidence, regime,
                         setup, risk, decision, summary, reasons)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """, (
                    image_hash, timeframe,
                    result_data.get("direction"), result_data.get("confidence"),
                    result_data.get("regime"), result_data.get("setup"),
                    result_data.get("risk"), result_data.get("decision"),
                    result_data.get("summary"),
                    json.dumps(result_data.get("reasons", []))
                ))
                row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as e:
        print(f"[vision] save error: {e}")
        return None

# ── PROMPT ────────────────────────────────────────────────────────────────────

BASE_PROMPT = """INSTRUÇÃO CRÍTICA: Responda APENAS com um objeto JSON válido. NENHUM texto, título, explicação ou markdown antes ou depois do JSON. Só o JSON.

Você é um sistema de análise técnica de elite para opções binárias M1/M5. Analise o gráfico internamente usando os critérios abaixo e preencha o JSON de saída.

ANÁLISE INTERNA (não escreva, só use para preencher o JSON):

A) ESTRUTURA: tendência alta (HH+HL) / baixa (LH+LL) / lateral? Quebra de estrutura (BOS)?

B) PADRÕES DE CANDLE (últimas 5 velas): doji, engolfo, martelo, shooting star, pin bar, harami, marubozu, three soldiers/crows, inside bar, dark cloud cover, piercing line, spinning top. Corpo vs sombra. Reversão ou continuação?

C) SPIKES E EXAUSTÃO (CRÍTICO):
   - Spike (vela muito maior que as anteriores) + velas menores depois = exaustão → PUT
   - Spike + volume explosivo = possível tendência → favor do spike
   - Vela de rejeição (sombra ≥2× corpo) em nível = sinal oposto à sombra
   - 3+ velas consecutivas = momentum confirmado nessa direção

D) SUPORTE/RESISTÊNCIA: topos, fundos, zonas de congestão, números redondos (2300, 84.00). Preço rompendo / rejeitando / consolidando?

E) VOLUME (só se histograma visível): spike no topo/fundo = reversão. Crescente = confirma. Decrescente = fraqueza.

F) MOMENTUM: velas ficando menores = fraqueza. Fechamento no topo = força CALL. Fechamento na base = força PUT.

G) INDICADORES (APENAS os visíveis no gráfico, nunca invente):
   - EMA acima = CALL | abaixo = PUT | cruzamento = mudança
   - Bollinger: toque na banda superior = PUT | inferior = CALL
   - RSI >70 = sobrecomprado (PUT) | <30 = sobrevendido (CALL) | divergência = reversão
   - MACD: cruzamento = mudança de momentum
   - Estocástico: >80 = PUT | <20 = CALL

H) PADRÕES GRÁFICOS: topo/fundo duplo, cabeça e ombros, triângulos, canal, bandeira, cunha ascendente=PUT, cunha descendente=CALL.

I) SESSÃO (se horário visível): asiática=baixa volatilidade, europeia/americana=alta. Spike em horário incomum = notícia → risco alto.

J) TIMING: segundos restantes no candle. 0-20s=agora, 21-45s=aguardar (próximo candle — PODE ser ENTRADA_FORTE se sinal é claro), 46-60s=evitar. "aguardar" NÃO significa dúvida, significa "entrar no próximo candle".

REGRAS DE VOTAÇÃO (100 votos totais entre call/put/observe):
- Spike + reversão confirmada → ≥80 votos no oposto ao spike
- 3+ velas consecutivas → ≥70 votos nessa direção
- Rejeição em S/R forte → ≥75 votos no sentido da rejeição
- RSI extremo + padrão de reversão → ≥72 votos
- Mercado lateral sem sinal → ≥60 votos em observe
- Confidence máximo = 95. Se confidence < 55: decision = OBSERVAR.

SAÍDA — retorne EXATAMENTE este JSON preenchido:
{"direction":"CALL ou PUT","confidence":0-95,"regime":"trend_up/trend_down/sideways/reversal/spike_reversal/chaotic","setup":"premium/standard/fraco","pattern":"nome do padrão identificado","entry_timing":"agora/aguardar/evitar","trend_strength":"forte/moderado/fraco","key_level":"nível chave mais próximo ou vazio","reasons":["price action e padrão","estrutura e S/R","volume e momentum","indicadores visíveis","timing e síntese"],"risk":"baixo/moderado/alto","decision":"ENTRADA_FORTE/ENTRADA_CAUTELA/OBSERVAR","summary":"frase curta objetiva","votes":{"call":0,"put":0,"observe":0}}
"""

# ── LOSS CAUSE ────────────────────────────────────────────────────────────────

def _infer_loss_cause(regime: str, setup: str, confidence: int, risk: str) -> str:
    regime = (regime or "").lower()
    if regime in ("sideways", "lateral"):
        return "sideways_noise"
    if regime == "chaotic":
        return "volatility_trap"
    if regime == "reversal":
        return "reversal_ignored"
    if (risk or "").lower() == "alto":
        return "volatility_trap"
    return "wrong_direction"

def _normalize_result(r: dict) -> dict:
    """Corrige typos e valores inválidos que o modelo pode gerar."""
    # entry_timing
    timing = str(r.get("entry_timing", "") or "").lower().strip()
    if "aguar" in timing:
        r["entry_timing"] = "aguardar"
    elif "evit" in timing or "avoid" in timing:
        r["entry_timing"] = "evitar"
    elif "agora" in timing or "now" in timing or "enter" in timing:
        r["entry_timing"] = "agora"
    elif timing not in ("agora", "aguardar", "evitar"):
        r["entry_timing"] = "aguardar"

    # regime
    regime = str(r.get("regime", "") or "").lower()
    if regime not in ("trend_up","trend_down","sideways","reversal","spike_reversal","chaotic"):
        if "spike" in regime:
            r["regime"] = "spike_reversal"
        elif "trend" in regime and ("up" in regime or "alta" in regime or "bull" in regime):
            r["regime"] = "trend_up"
        elif "trend" in regime and ("down" in regime or "baixa" in regime or "bear" in regime):
            r["regime"] = "trend_down"
        elif "revers" in regime:
            r["regime"] = "reversal"
        elif "later" in regime or "side" in regime or "consol" in regime:
            r["regime"] = "sideways"
        elif "caot" in regime or "chaot" in regime or "chaos" in regime:
            r["regime"] = "chaotic"

    # trend_strength
    strength = str(r.get("trend_strength", "") or "").lower()
    if strength not in ("forte","moderado","fraco"):
        if "strong" in strength or "fort" in strength:
            r["trend_strength"] = "forte"
        elif "weak" in strength or "fraco" in strength or "fraq" in strength:
            r["trend_strength"] = "fraco"
        else:
            r["trend_strength"] = "moderado"

    # setup
    setup = str(r.get("setup", "") or "").lower()
    if setup not in ("premium","standard","fraco"):
        if "prem" in setup:
            r["setup"] = "premium"
        elif "fraco" in setup or "weak" in setup or "poor" in setup:
            r["setup"] = "fraco"
        else:
            r["setup"] = "standard"

    # decision
    dec = str(r.get("decision", "") or "").upper()
    if dec not in ("ENTRADA_FORTE","ENTRADA_CAUTELA","OBSERVAR"):
        if "FORTE" in dec or "STRONG" in dec:
            r["decision"] = "ENTRADA_FORTE"
        elif "CAUT" in dec or "LIMIT" in dec:
            r["decision"] = "ENTRADA_CAUTELA"
        else:
            r["decision"] = "OBSERVAR"

    # confidence clamp
    try:
        r["confidence"] = max(0, min(95, int(r.get("confidence", 50) or 50)))
    except (TypeError, ValueError):
        r["confidence"] = 50

    return r

# ── ROUTES ────────────────────────────────────────────────────────────────────

@bp.post("/vision/analyze")
def analyze():
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "Nenhuma imagem enviada"}), 400
    file = request.files["image"]
    mime = file.mimetype or "image/jpeg"
    if mime not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        mime = "image/jpeg"
    image_bytes = file.read()
    image_data  = base64.standard_b64encode(image_bytes).decode("utf-8")
    image_hash  = hashlib.md5(image_bytes).hexdigest()
    timeframe   = request.form.get("timeframe", "M1")

    stats   = _get_stats()
    context = _build_context(stats, timeframe)
    prompt  = BASE_PROMPT + context

    result = None
    last_error = ""
    provider_used = ""

    if GROQ_API_KEY:
        try:
            result = _groq(image_data, mime, prompt)
            provider_used = "groq"
        except Exception as e:
            last_error = str(e)

    if result is None and GEMINI_API_KEY:
        try:
            result = _gemini(image_data, mime, prompt)
            provider_used = "gemini"
        except Exception as e:
            last_error = str(e)

    if result is None:
        return jsonify({"ok": False, "error": last_error or "Todos provedores falharam"}), 500

    # Persiste no banco dedicado (contexto adaptativo futuro)
    result = _normalize_result(result)

    # Calcula horário de entrada e expiração no fuso de Brasília (UTC-3)
    now_brt = datetime.now(tz=timezone(timedelta(hours=-3)))
    expiry_minutes = 1 if timeframe == "M1" else 5
    timing = result.get("entry_timing", "aguardar")
    next_minute = (now_brt + timedelta(minutes=1)).replace(second=0, microsecond=0)
    if timing == "agora":
        # Entra no PRÓXIMO minuto completo (usuário precisa de tempo para abrir a corretora)
        entry_dt = next_minute
        expiry_dt = entry_dt + timedelta(minutes=expiry_minutes)
    elif timing == "aguardar":
        # Aguarda mais um candle: entra no minuto seguinte ao próximo
        entry_dt = next_minute + timedelta(minutes=1)
        expiry_dt = entry_dt + timedelta(minutes=expiry_minutes)
    else:  # evitar
        entry_dt = None
        expiry_dt = None
    result["entry_time"]      = entry_dt.strftime("%H:%M") if entry_dt else None
    result["expiry_time"]     = expiry_dt.strftime("%H:%M") if expiry_dt else None
    result["expiry_duration"] = f"{expiry_minutes} min"

    db_id = _save(image_hash, timeframe, result)
    result["analysis_id"] = db_id

    # Também salva no KV store para enriquecimento no feedback
    kv_id = uuid.uuid4().hex[:16]
    now_ts = time.time()
    try:
        store = get_state_store()
        store.upsert_collection_item(VISION_COLLECTION, kv_id, {
            "uid": kv_id, "db_id": db_id, "created_at_ts": now_ts,
            "timeframe": timeframe, "provider": provider_used,
            "direction": result.get("direction", ""),
            "confidence": result.get("confidence", 0),
            "regime": result.get("regime", "unknown"),
            "setup": result.get("setup", ""),
            "risk": result.get("risk", ""),
            "decision": result.get("decision", ""),
            "reasons": result.get("reasons", []),
            "result": None,
        })
    except Exception:
        pass

    if stats and stats["overall"].get("total"):
        o = stats["overall"]
        t = int(o.get("total") or 0)
        w = int(o.get("wins") or 0)
        result["stats"] = {"total": t, "win_rate": round(w / t * 100) if t > 0 else 0}

    return jsonify({"ok": True, "result": result, "kv_id": kv_id, "provider": provider_used})


@bp.post("/vision/feedback")
def feedback():
    body = request.get_json(force=True, silent=True) or {}
    result = str(body.get("result", "")).upper().strip()
    if result not in ("WIN", "LOSS"):
        return jsonify({"ok": False, "error": "result deve ser WIN ou LOSS"}), 400

    analysis_id = body.get("analysis_id")   # numeric DB id
    kv_id       = str(body.get("kv_id", "") or "").strip()
    direction   = str(body.get("direction", "CALL")).upper()
    regime      = str(body.get("regime", "unknown")).lower()
    setup       = str(body.get("setup", "standard")).lower()
    confidence  = int(body.get("confidence", 65) or 65)
    risk        = str(body.get("risk", "moderado")).lower()
    timeframe   = str(body.get("timeframe", "M1"))
    reasons     = list(body.get("reasons", []) or [])
    provider    = str(body.get("provider", "vision_ai"))
    outcome_lower = result.lower()

    # 1. Atualiza vision_analyses table
    if analysis_id and DATABASE_URL:
        try:
            with _db() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE vision_analyses SET result=%s WHERE id=%s",
                                (outcome_lower, analysis_id))
                conn.commit()
        except Exception as e:
            print(f"[vision] feedback db error: {e}")

    # 2. Enriquece do KV store
    if kv_id:
        try:
            store = get_state_store()
            for row in store.list_collection(VISION_COLLECTION, limit=200):
                if row.get("uid") == kv_id:
                    direction  = direction  or str(row.get("direction", "CALL")).upper()
                    regime     = regime     or str(row.get("regime", "unknown")).lower()
                    setup      = setup      or str(row.get("setup", "standard")).lower()
                    confidence = confidence or int(row.get("confidence", 65) or 65)
                    risk       = risk       or str(row.get("risk", "moderado")).lower()
                    timeframe  = timeframe  or str(row.get("timeframe", "M1"))
                    reasons    = reasons    or list(row.get("reasons", []) or [])
                    provider   = provider   or str(row.get("provider", "vision_ai"))
                    store.upsert_collection_item(VISION_COLLECTION, kv_id,
                        {**row, "result": result, "evaluated_at_ts": time.time()})
                    break
        except Exception:
            pass

    now_ts      = time.time()
    now_str     = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%H:%M")
    hour_bucket = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%H:00")
    uid         = kv_id or f"vision-{direction}-{now_str}"
    loss_cause  = "none" if result == "WIN" else _infer_loss_cause(regime, setup, confidence, risk)

    trade_payload = {
        "uid": uid, "asset": "VISION_MANUAL", "direction": direction,
        "signal": direction, "result": result, "loss_cause": loss_cause,
        "regime": regime, "setup_quality": setup, "confidence": confidence,
        "timeframe": timeframe, "provider": provider, "market_type": "manual_vision",
        "hour_bucket": hour_bucket, "analysis_time": now_str,
        "created_at_ts": now_ts, "evaluated_at_ts": now_ts,
        "source": "vision_feedback", "reasons": reasons,
    }

    # 3. Registra no EdgeAuditEngine + JournalManager (aparece nos Stats)
    try:
        EdgeAuditEngine().record_trade(trade_payload)
        JournalManager().add_trade(trade_payload)
    except Exception:
        pass

    # 4. Alimenta LearningEngine
    try:
        LearningEngine().register_outcome(
            asset="VISION_MANUAL", direction=direction, regime=regime,
            specialist="vision_ai", provider=provider, market_type="manual_vision",
            hour_bucket=hour_bucket, setup_quality=setup, result=result,
            loss_cause=loss_cause, operating_state="ENTRADA_FORTE", signal_type="vision",
        )
    except Exception:
        pass

    return jsonify({"ok": True, "result_registered": result, "loss_cause": loss_cause})


@bp.post("/vision/result")
def save_result():
    """Alias legado — mantido para compatibilidade."""
    data = request.get_json(force=True, silent=True) or {}
    analysis_id = data.get("analysis_id")
    outcome = str(data.get("result", "")).lower()
    if not analysis_id or outcome not in ("win", "loss"):
        return jsonify({"ok": False, "error": "Parâmetros inválidos"}), 400
    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Banco não configurado"}), 500
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE vision_analyses SET result=%s WHERE id=%s",
                            (outcome, analysis_id))
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/vision/stats")
def get_stats():
    stats = _get_stats()
    if not stats:
        return jsonify({"ok": False, "error": "Sem dados"})
    return jsonify({"ok": True, "stats": stats})
