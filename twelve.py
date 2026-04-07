from __future__ import annotations

from typing import Dict, List

from alpha_hive.core.contracts import Candle

def normalize(values: List[Dict[str, str]]) -> List[Candle]:
    return [
        Candle(
            ts=row.get("datetime", ""),
            open=float(row.get("open", 0.0)),
            high=float(row.get("high", 0.0)),
            low=float(row.get("low", 0.0)),
            close=float(row.get("close", 0.0)),
            volume=float(row.get("volume", 0.0) or 0.0),
        )
        for row in values
    ]
