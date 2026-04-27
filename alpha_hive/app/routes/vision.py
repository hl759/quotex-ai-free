from __future__ import annotations
import base64, json, os, re, hashlib
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

bp = Blueprint("vision", __name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "").strip()
DATABASE_URL   = os.getenv("DATABASE_URL", "").strip()

# ── DB ───────────────────────────────────────────────────────────────────────

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

# ── STATS / CONTEXT ──────────────────────────────────────────────────────────

def _get_stats():
    """Busca estatísticas dos últimos 200 resultados para montar contexto adaptativo."""
    if not DATABASE_URL:
        return None
    try:
        with _db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Total e win rate geral
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                        ROUND(AVG(confidence)) as avg_confidence
                    FROM vision_analyses
                    WHERE result IN ('win','loss')
                    ORDER BY created_at DESC
                    LIMIT 200
                """)
                overall = cur.fetchone()

                # Win rate por regime
                cur.execute("""
                    SELECT regime,
                        COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins
                    FROM vision_analyses
                    WHERE result IN ('win','loss') AND regime IS NOT NULL
                    GROUP BY regime ORDER BY total DESC LIMIT 10
                """)
                by_regime = cur.fetchall()

                # Win rate por setup
                cur.execute("""
                    SELECT setup,
                        COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins
                    FROM vision_analyses
                    WHERE result IN ('win','loss') AND setup IS NOT NULL
                    GROUP BY setup ORDER BY total DESC
                """)
                by_setup = cur.fetchall()

                # Win rate por direção
                cur.execute("""
                    SELECT direction,
                        COUNT(*) as total,
                        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins
                    FROM vision_analyses
                    WHERE result IN ('win','loss') AND direction IS NOT NULL
                    GROUP BY direction
                """)
                by_direction = cur.fetchall()

                # Últimas 10 análises para padrão recente
                cur.execute("""
                    SELECT direction, regime, setup, confidence, result, summary
                    FROM vision_analyses
                    WHERE result IN ('win','loss')
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
    """Monta o contexto adaptativo com 'memória coletiva' dos trades anteriores."""
    if not stats or not stats["overall"].get("total"):
        return ""

    o = stats["overall"]
    total = int(o.get("total") or 0)
    if total == 0:
        return ""

    wins = int(o.get("wins") or 0)
    losses = int(o.get("losses") or 0)
    wr = round(wins / total * 100) if total > 0 else 0

    lines = [f"\n\n=== MEMÓRIA COLETIVA DE {min(total,100)} TRADERS ==="]
    lines.append(f"Win rate geral: {wr}% ({wins}W/{losses}L de {total} operações)")

    if stats["by_regime"]:
        lines.append("\nPerformance por regime de mercado:")
        for r in stats["by_regime"]:
            t = int(r["total"] or 0)
            w = int(r["wins"] or 0)
            pct = round(w/t*100) if t > 0 else 0
            flag = "✅" if pct >= 60 else "⚠️" if pct >= 45 else "❌"
            lines.append(f"  {flag} {r['regime']}: {pct}% win ({t} ops)")

    if stats["by_setup"]:
        lines.append("\nPerformance por setup:")
        for r in stats["by_setup"]:
            t = int(r["total"] or 0)
            w = int(r["wins"] or 0)
            pct = round(w/t*100) if t > 0 else 0
            flag = "✅" if pct >= 60 else "⚠️" if pct >= 45 else "❌"
            lines.append(f"  {flag} {r['setup']}: {pct}% win ({t} ops)")

    if stats["by_direction"]:
        lines.append("\nPerformance por direção:")
        for r in stats["by_direction"]:
            t = int(r["total"] or 0)
            w = int(r["wins"] or 0)
            pct = round(w/t*100) if t > 0 else 0
            lines.append(f"  {'📈' if r['direction']=='CALL' else '📉'} {r['direction']}: {pct}% win ({t} ops)")

    if stats["recent"]:
        lines.append("\nÚltimas operações (padrão recente):")
        for r in stats["recent"]:
            icon = "✅" if r["result"] == "win" else "❌"
            lines.append(f"  {icon} {r['direction']} | {r['regime']} | {r['setup']} | {r['confidence']}% conf")

    lines.append("\nUSE ESSES DADOS para calibrar sua análise. Se um regime/setup tem win rate baixo, seja mais conservador ou mude a direção. Se tem win rate alto, pode ser mais agressivo na confiança.")
    lines.append("=== FIM DA MEMÓRIA ===")
    return "\n".join(lines)

# ── PARSING ──────────────────────────────────────────────────────────────────

def _parse(raw):
    raw = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
    raw = re.sub(r"```$", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return json.loads(m.group(0) if m else raw)

# ── PROVIDERS ────────────────────────────────────────────────────────────────

def _groq(image_data, mime, prompt):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json={
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                {"type": "text", "text": prompt}
            ]}],
            "max_tokens": 600,
            "temperature": 0.1
        },
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        timeout=30
    )
    r.raise_for_status()
    return _parse(r.json()["choices"][0]["message"]["content"])

def _gemini(image_data, mime, prompt):
    for model in ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro-vision"]:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                json={"contents": [{"parts": [
                    {"inline_data": {"mime_type": mime, "data": image_data}},
                    {"text": prompt}
                ]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600}},
                params={"key": GEMINI_API_KEY},
                timeout=45
            )
            if r.status_code in (429, 404): continue
            r.raise_for_status()
            d = r.json()
            if not d.get("candidates"): continue
            return _parse(d["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:
            continue
    return None

# ── SAVE ─────────────────────────────────────────────────────────────────────

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
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (
                    image_hash, timeframe,
                    result_data.get("direction"),
                    result_data.get("confidence"),
                    result_data.get("regime"),
                    result_data.get("setup"),
                    result_data.get("risk"),
                    result_data.get("decision"),
                    result_data.get("summary"),
                    json.dumps(result_data.get("reasons", []))
                ))
                row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as e:
        print(f"[vision] save error: {e}")
        return None

# ── ROUTES ───────────────────────────────────────────────────────────────────

BASE_PROMPT = """Você é um conselho de 100 traders experientes analisando um gráfico de opções binárias em tempo real.

Cada trader vota independentemente e você retorna o consenso do grupo.

Retorne APENAS JSON válido sem markdown:
{"direction":"CALL ou PUT","confidence":0-100,"regime":"trend/sideways/reversal/chaotic","setup":"premium/standard/fraco","reasons":["razão detalhada 1","razão detalhada 2","razão detalhada 3"],"risk":"baixo/moderado/alto","decision":"ENTRADA_FORTE/ENTRADA_CAUTELA/OBSERVAR","summary":"resumo em uma frase"}

Regras de consenso:
- CALL: maioria vê momentum de alta, suporte segurando, candles verdes dominando
- PUT: maioria vê momentum de baixa, resistência segurando, candles vermelhos dominando  
- OBSERVAR: traders divididos, mercado lateral, padrão ambíguo
- Confiança 76-100 = ENTRADA_FORTE (80%+ dos traders concordam)
- Confiança 55-75 = ENTRADA_CAUTELA (60-79% concordam)
- Confiança <55 = OBSERVAR (menos de 60% concordam)
- Analise: estrutura de candles, tendência, volume, padrões de reversão/continuação, suporte/resistência
"""

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

    # Busca estatísticas adaptativas do banco
    stats   = _get_stats()
    context = _build_context(stats, timeframe)
    prompt  = BASE_PROMPT + context

    result     = None
    last_error = ""

    if GROQ_API_KEY:
        try:
            result = _groq(image_data, mime, prompt)
        except Exception as e:
            last_error = str(e)

    if result is None and GEMINI_API_KEY:
        try:
            result = _gemini(image_data, mime, prompt)
        except Exception as e:
            last_error = str(e)

    if result is None:
        return jsonify({"ok": False, "error": last_error or "Todos provedores falharam"}), 500

    # Salva no banco para aprendizado futuro
    analysis_id = _save(image_hash, timeframe, result)
    result["analysis_id"] = analysis_id

    # Inclui estatísticas no retorno para mostrar na UI
    if stats and stats["overall"].get("total"):
        o = stats["overall"]
        t = int(o.get("total") or 0)
        w = int(o.get("wins") or 0)
        result["stats"] = {
            "total": t,
            "win_rate": round(w / t * 100) if t > 0 else 0
        }

    return jsonify({"ok": True, "result": result})


@bp.post("/vision/result")
def save_result():
    """Salva Win ou Loss de uma análise anterior."""
    data = request.get_json()
    analysis_id = data.get("analysis_id")
    outcome     = data.get("result", "").lower()

    if not analysis_id or outcome not in ("win", "loss"):
        return jsonify({"ok": False, "error": "Parâmetros inválidos"}), 400

    if not DATABASE_URL:
        return jsonify({"ok": False, "error": "Banco não configurado"}), 500

    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE vision_analyses SET result=%s WHERE id=%s",
                    (outcome, analysis_id)
                )
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
