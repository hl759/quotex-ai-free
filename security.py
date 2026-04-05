
import json


def mask_secret(value, visible_prefix=4, visible_suffix=4):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= visible_prefix + visible_suffix:
        return "*" * len(text)
    return f"{text[:visible_prefix]}{'*' * max(4, len(text) - visible_prefix - visible_suffix)}{text[-visible_suffix:]}"


def sanitize_error(exc):
    text = str(exc or "unknown_error").strip()
    if not text:
        text = "unknown_error"
    return text[:300]


def json_body(request):
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def safe_json_dumps(data):
    return json.dumps(data, ensure_ascii=False, default=str)
