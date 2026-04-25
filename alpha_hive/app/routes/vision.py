from __future__ import annotations
import base64, json, os, re, time
import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("vision", __name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

PROMPT = """Analise este gráfico de opções binárias e retorne APENAS JSON sem markdown:
{"direction":"CALL ou PUT","confidence":0-100,"regime":"trend/sideways/reversal/chaotic","setup":"premium/standard/fraco","reasons":["r1","r2","r3"],"risk":"baixo/moderado/alto","decision":"ENTRADA_FORTE/ENTRADA_CAUTELA/OBSERVAR","summary":"frase curta"}
CALL=alta. PUT=baixa. Confiança>75=ENTRADA_FORTE, 55-75=ENTRADA_CAUTELA, <55=OBSERVAR. SOMENTE JSON."""

MODELS = [
    "gemini-pro-vision",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash-8b",
]

def _parse(raw):
    raw = re.sub(r"^```(?:json)?","",raw.strip()).strip()
    raw = re.sub(r"```$","",raw).strip()
    m = re.search(r"\{.*\}",raw,re.DOTALL)
    return json.loads(m.group(0) if m else raw)

@bp.post("/vision/analyze")
def analyze():
    if not GEMINI_API_KEY:
        return jsonify({"ok":False,"error":"GEMINI_API_KEY não configurada"}),500
    if "image" not in request.files:
        return jsonify({"ok":False,"error":"Nenhuma imagem enviada"}),400

    file = request.files["image"]
    mime = file.mimetype or "image/jpeg"
    if mime not in {"image/jpeg","image/jpg","image/png","image/webp"}: mime="image/jpeg"
    image_data = base64.standard_b64encode(file.read()).decode("utf-8")

    last_error = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents":[{"parts":[
                {"inline_data":{"mime_type":mime,"data":image_data}},
                {"text":PROMPT}
            ]}],
            "generationConfig":{"temperature":0.1,"maxOutputTokens":512}
        }
        try:
            r = requests.post(url,json=payload,params={"key":GEMINI_API_KEY},timeout=45)
            if r.status_code == 429:
                last_error = f"{model}: limite atingido"
                time.sleep(2)
                continue
            if r.status_code == 404:
                last_error = f"{model}: não disponível"
                continue
            r.raise_for_status()
            d = r.json()
            candidates = d.get("candidates",[])
            if not candidates:
                last_error = f"{model}: sem resposta"
                continue
            raw = candidates[0]["content"]["parts"][0]["text"]
            return jsonify({"ok":True,"result":_parse(raw),"model":model})
        except json.JSONDecodeError as e:
            last_error = f"{model}: JSON inválido - {e}"
            continue
        except Exception as e:
            last_error = f"{model}: {e}"
            continue

    return jsonify({"ok":False,"error":f"Todos os modelos falharam. Último erro: {last_error}"}),500
