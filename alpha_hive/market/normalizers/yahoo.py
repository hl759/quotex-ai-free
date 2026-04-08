from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from alpha_hive.core.contracts import Candle

def normalize(payload: Dict[str, Any], limit: int = 50) -> List[Candle]:
    try:
        result = (((payload or {}).get("chart") or {}).get("result") or [None])[0] or {}
        timestamps = result.get("timestamp") or []
        quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
    except Exception:
        return []
    out: List[Candle] = []
    for i, ts in enumerate(timestamps):
        if i >= len(opens) or i >= len(highs) or i >= len(lows) or i >= len(closes):
            continue
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if None in (o, h, l, c):
            continue
        v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0
        out.append(Candle(
            ts=datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            open=float(o), high=float(h), low=float(l), close=float(c), volume=float(v),
        ))
    return out[-max(10, int(limit)):]
