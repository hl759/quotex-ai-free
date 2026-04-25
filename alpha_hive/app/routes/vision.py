from __future__ import annotations
import base64, json, os, re
import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("vision", __name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

PROMPT = """Você é especialista em opções binárias M1/M5. Analise o gráfico e retorne APENAS JSON válido sem markdown:
{"direction":"CALL ou PUT","confidence":0-100,"regime":"trend/sideways/reversal/chaotic","setup":"premium/standard/fraco","reasons":["r1","r2","r3"],"risk":"baixo/moderado/alto","decision":"ENTRADA_FORTE/ENTRADA_CAUTELA/OBSERVAR","summary":"frase curta"}
CALL=tendência de alta. PUT=tendência de baixa. OBSERVAR=indefinido. Confiança>75=ENTRADA_FORTE, 55-75=ENTRADA_CAUTELA, <55=OBSERVAR. Retorne SOMENTE o JSON."""

def _parse_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m: raw = m.group(0)
    return json.loads(raw)

def _try_gemini(image_data, mime):
    for model in ["gemini-1.5-flash", "gemini-1.5-pro"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents":[{"parts":[{"inline_data":{"mime_type":mime,"data":image_data}},{"text":PROMPT}]}],
            "generationConfig":{"temperature":0.1,"maxOutputTokens":512}
        }
        try:
            r = requests.post(url, json=payload, params={"key":GEMINI_API_KEY}, timeout=30)
            if r.status_code == 429: continue
            r.raise_for_status()
            d = r.json()
            raw = d["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_json(raw)
        except Exception:
            continue
    return None

def _try_openrouter(image_data, mime):
    payload = {
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{
            "role": "user",
            "content": [
                {"type":"image_url","image_url":{"url":f"data:{mime};base64,{image_data}"}},
                {"type":"text","text":PROMPT}
            ]
        }],
        "max_tokens": 512
    }
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://quotex-ai-free-mr8n.onrender.com",
        },
        timeout=30
    )
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    return _parse_json(raw)

@bp.post("/vision/analyze")
def analyze():
    if "image" not in request.files:
        return jsonify({"ok":False,"error":"Nenhuma imagem enviada"}),400
    file = request.files["image"]
    mime = file.mimetype or "image/jpeg"
    if mime not in {"image/jpeg","image/jpg","image/png","image/webp"}: mime="image/jpeg"
    image_data = base64.standard_b64encode(file.read()).decode("utf-8")

    result = None
    error = ""

    # Tenta Gemini primeiro
    if GEMINI_API_KEY:
        try:
            result = _try_gemini(image_data, mime)
        except Exception as e:
            error = str(e)

    # Fallback: OpenRouter
    if result is None and OPENROUTER_API_KEY:
        try:
            result = _try_openrouter(image_data, mime)
        except Exception as e:
            error = str(e)

    if result is None:
        return jsonify({"ok":False,"error": error or "Todos os provedores falharam"}),500

    return jsonify({"ok":True,"result":result})
