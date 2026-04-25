from __future__ import annotations
import base64, json, os, re
import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("vision", __name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.0-pro-vision-latest:generateContent"
PROMPT = """Você é um analista especialista em opções binárias M1.
Analise o gráfico e retorne APENAS JSON válido, sem markdown:
{"direction":"CALL ou PUT","confidence":0-100,"regime":"trend/sideways/reversal/chaotic","setup":"premium/standard/fraco","reasons":["r1","r2","r3"],"risk":"baixo/moderado/alto","decision":"ENTRADA_FORTE/ENTRADA_CAUTELA/OBSERVAR","summary":"frase curta"}
Regras: CALL=candles subindo/médias para cima. PUT=candles descendo/médias para baixo. OBSERVAR=lateral/ambíguo. Confiança>75=ENTRADA_FORTE, 55-75=ENTRADA_CAUTELA, <55=OBSERVAR. Retorne SOMENTE o JSON."""

@bp.post("/vision/analyze")
def analyze():
    if not GEMINI_API_KEY:
        return jsonify({"ok":False,"error":"GEMINI_API_KEY não configurada"}),500
    if "image" not in request.files:
        return jsonify({"ok":False,"error":"Nenhuma imagem enviada"}),400
    file = request.files["image"]
    mime = file.mimetype or "image/jpeg"
    if mime not in {"image/jpeg","image/jpg","image/png","image/webp"}:
        mime = "image/jpeg"
    image_data = base64.standard_b64encode(file.read()).decode("utf-8")
    payload = {"contents":[{"parts":[{"inline_data":{"mime_type":mime,"data":image_data}},{"text":PROMPT}]}],"generationConfig":{"temperature":0.1,"maxOutputTokens":512}}
    try:
        resp = requests.post(GEMINI_URL,json=payload,params={"key":GEMINI_API_KEY},headers={"Content-Type":"application/json"},timeout=30)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            reason = data.get("promptFeedback", {}).get("blockReason", "resposta vazia")
            return jsonify({"ok": False, "error": f"Gemini bloqueou: {reason}", "raw": str(data)[:300]}), 500
        raw = candidates[0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r"^```(?:json)?","",raw).strip()
        raw = re.sub(r"```$","",raw).strip()
        match = re.search(r"\{.*\}",raw,re.DOTALL)
        if match: raw = match.group(0)
        return jsonify({"ok":True,"result":json.loads(raw)})
    except json.JSONDecodeError as e:
        return jsonify({"ok":False,"error":f"JSON inválido: {e}","raw":raw[:200]}),500
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500
