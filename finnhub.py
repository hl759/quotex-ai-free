from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from alpha_hive.core.contracts import Candle

def normalize(data: Dict[str, list]) -> List[Candle]:
    if data.get("s") != "ok" or not data.get("c"):
        return []
    out: List[Candle] = []
    for i in range(len(data["c"])):
        out.append(
            Candle(
                ts=datetime.utcfromtimestamp(data["t"][i]).strftime("%Y-%m-%d %H:%M:%S"),
                open=float(data["o"][i]),
                high=float(data["h"][i]),
                low=float(data["l"][i]),
                close=float(data["c"][i]),
                volume=float(data["v"][i] if i < len(data["v"]) else 0),
            )
        )
    out.reverse()
    return out
