from __future__ import annotations
import base64, json, os, re, time, uuid
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, request

from alpha_hive.audit.edge_audit import EdgeAuditEngine
from alpha_hive.audit.journal_manager import JournalManager
from alpha_hive.learning.learning_engine import LearningEngine
from alpha_hive.storage.state_store import get_state_store

bp = Blueprint("vision", __name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

VISION_COLLECTION = "vision_analyses_v1"

PROMPT = """Analise este grafico de opcoes binarias e retorne APENAS JSON sem markdown:
{"direction":"CALL ou PUT","confidence":0-100,"regime":"trend/sideways/reversal/chaotic","setup":"premium/standard/fraco","reasons":["r1","r2","r3"],"risk":"baixo/moderado/alto","decision":"ENTRADA_FORTE/ENTRADA_CAUTELA/OBSERVAR","summary":"frase curta"}
CALL=alta. PUT=baixa. Confianca>75=ENTRADA_FORTE, 55-75=ENTRADA_CAUTELA, <55=OBSERVAR. SOMENTE JSON."""

def _parse(raw):
    raw = re.sub(r"^```(?:json)?","",raw.strip()).strip()
    raw = re.sub(r"```$","",raw).strip()
    m = re.search(r"\{.*\}",raw,re.DOTALL)
    return json.loads(m.group(0) if m else raw)

def _gemini(image_data, mime):
    for model in ["gemini-1.5-pro","gemini-1.5-flash","gemini-pro-vision"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = requests.post(url, json={
                "contents":[{"parts":[{"inline_data":{"mime_type":mime,"data":image_data}},{"text":PROMPT}]}],
                "generationConfig":{"temperature":0.1,"maxOutputTokens":512}
            }, params={"key":GEMINI_API_KEY}, timeout=45)
            if r.status_code in (429,404): continue
            r.raise_for_status()
            d = r.json()
            if not d.get("candidates"): continue
            return _parse(d["candidates"][0]["content"]["parts"][0]["text"])
        except: continue
    return None

def _groq(image_data, mime):
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", json={
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages":[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:{mime};base64,{image_data}"}},
            {"type":"text","text":PROMPT}
        ]}],
        "max_tokens": 512, "temperature": 0.1
    }, headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"}, timeout=30)
    r.raise_for_status()
    return _parse(r.json()["choices"][0]["message"]["content"])

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
    if (setup or "").lower() == "fraco":
        return "wrong_direction"
    return "wrong_direction"

@bp.post("/vision/analyze")
def analyze():
    if "image" not in request.files:
        return jsonify({"ok":False,"error":"Nenhuma imagem enviada"}),400
    file = request.files["image"]
    mime = file.mimetype or "image/jpeg"
    if mime not in {"image/jpeg","image/jpg","image/png","image/webp"}: mime="image/jpeg"
    image_data = base64.standard_b64encode(file.read()).decode("utf-8")
    result = None
    last_error = ""
    provider_used = ""
    if GEMINI_API_KEY:
        try:
            result = _gemini(image_data, mime)
            provider_used = "gemini"
        except Exception as e: last_error = str(e)
    if result is None and GROQ_API_KEY:
        try:
            result = _groq(image_data, mime)
            provider_used = "groq"
        except Exception as e: last_error = str(e)
    if result is None:
        return jsonify({"ok":False,"error":last_error or "Todos provedores falharam"}),500

    analysis_id = uuid.uuid4().hex[:16]
    timeframe = request.form.get("timeframe", "M1")
    now_ts = time.time()
    now_str = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%H:%M")

    try:
        store = get_state_store()
        store.upsert_collection_item(VISION_COLLECTION, analysis_id, {
            "uid": analysis_id,
            "created_at_ts": now_ts,
            "analysis_time": now_str,
            "timeframe": timeframe,
            "provider": provider_used,
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

    return jsonify({"ok":True,"result":result,"analysis_id":analysis_id,"provider":provider_used})


@bp.post("/vision/feedback")
def feedback():
    body = request.get_json(force=True, silent=True) or {}
    analysis_id = str(body.get("analysis_id", "")).strip()
    result = str(body.get("result", "")).upper().strip()

    if result not in ("WIN", "LOSS"):
        return jsonify({"ok":False,"error":"result deve ser WIN ou LOSS"}), 400

    direction = str(body.get("direction", "CALL")).upper()
    regime = str(body.get("regime", "unknown")).lower()
    setup = str(body.get("setup", "standard")).lower()
    confidence = int(body.get("confidence", 65) or 65)
    risk = str(body.get("risk", "moderado")).lower()
    timeframe = str(body.get("timeframe", "M1"))
    reasons = list(body.get("reasons", []) or [])
    provider = str(body.get("provider", "vision_ai"))

    # Enrich from saved analysis and mark it with outcome
    if analysis_id:
        try:
            store = get_state_store()
            for row in store.list_collection(VISION_COLLECTION, limit=500):
                if row.get("uid") == analysis_id:
                    direction = direction or str(row.get("direction", "CALL")).upper()
                    regime = regime or str(row.get("regime", "unknown")).lower()
                    setup = setup or str(row.get("setup", "standard")).lower()
                    confidence = confidence or int(row.get("confidence", 65) or 65)
                    risk = risk or str(row.get("risk", "moderado")).lower()
                    timeframe = timeframe or str(row.get("timeframe", "M1"))
                    reasons = reasons or list(row.get("reasons", []) or [])
                    provider = provider or str(row.get("provider", "vision_ai"))
                    store.upsert_collection_item(VISION_COLLECTION, analysis_id,
                        {**row, "result": result, "evaluated_at_ts": time.time()})
                    break
        except Exception:
            pass

    now_ts = time.time()
    now_str = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%H:%M")
    hour_bucket = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%H:00")
    uid = analysis_id or f"vision-{direction}-{now_str}"
    loss_cause = "none" if result == "WIN" else _infer_loss_cause(regime, setup, confidence, risk)

    trade_payload = {
        "uid": uid,
        "asset": "VISION_MANUAL",
        "direction": direction,
        "signal": direction,
        "result": result,
        "loss_cause": loss_cause,
        "regime": regime,
        "setup_quality": setup,
        "confidence": confidence,
        "timeframe": timeframe,
        "provider": provider,
        "market_type": "manual_vision",
        "hour_bucket": hour_bucket,
        "analysis_time": now_str,
        "created_at_ts": now_ts,
        "evaluated_at_ts": now_ts,
        "source": "vision_feedback",
        "reasons": reasons,
    }

    try:
        EdgeAuditEngine().record_trade(trade_payload)
        JournalManager().add_trade(trade_payload)
    except Exception:
        pass

    try:
        learning = LearningEngine()
        learning.register_outcome(
            asset="VISION_MANUAL",
            direction=direction,
            regime=regime,
            specialist="vision_ai",
            provider=provider,
            market_type="manual_vision",
            hour_bucket=hour_bucket,
            setup_quality=setup,
            result=result,
            loss_cause=loss_cause,
            operating_state="ENTRADA_FORTE",
            signal_type="vision",
        )
    except Exception:
        pass

    return jsonify({"ok": True, "result_registered": result, "loss_cause": loss_cause})
