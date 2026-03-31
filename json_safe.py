import json
import math
from datetime import date, datetime, time
from decimal import Decimal


def to_jsonable(value):
    if value is None:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        try:
            f = float(value)
            return f if math.isfinite(f) else None
        except Exception:
            return None
    if isinstance(value, (datetime, date, time)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return to_jsonable(value.item())
        if isinstance(value, np.ndarray):
            return to_jsonable(value.tolist())
    except Exception:
        pass
    try:
        import pandas as pd
        if value is pd.NA:
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if hasattr(value, 'tolist'):
        try:
            return to_jsonable(value.tolist())
        except Exception:
            pass
    if hasattr(value, 'item'):
        try:
            return to_jsonable(value.item())
        except Exception:
            pass
    try:
        return str(value)
    except Exception:
        return None


def safe_dumps(value, **kwargs):
    kwargs.setdefault('ensure_ascii', False)
    kwargs.setdefault('allow_nan', False)
    return json.dumps(to_jsonable(value), **kwargs)


def safe_dump(value, fp, **kwargs):
    kwargs.setdefault('ensure_ascii', False)
    kwargs.setdefault('allow_nan', False)
    return json.dump(to_jsonable(value), fp, **kwargs)
