from __future__ import annotations
import base64, json, os, re, time
import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("vision", __name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

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
    if GEMINI_API_KEY:
        try: result = _gemini(image_data, mime)
        except Exception as e: last_error = str(e)
    if result is None and GROQ_API_KEY:
        try: result = _groq(image_data, mime)
        except Exception as e: last_error = str(e)
    if result is None:
        return jsonify({"ok":False,"error":last_error or "Todos provedores falharam"}),500
    return jsonify({"ok":True,"result":result})
