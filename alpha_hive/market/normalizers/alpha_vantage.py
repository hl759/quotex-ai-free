from __future__ import annotations

from typing import Dict, List

from alpha_hive.core.contracts import Candle

def normalize(data: Dict[str, dict]) -> List[Candle]:
    series = data.get("Time Series FX (1min)", {})
    out: List[Candle] = []
    for dt_str, row in list(series.items())[:50]:
        out.append(
            Candle(
                ts=dt_str,
                open=float(row.get("1. open", 0.0)),
                high=float(row.get("2. high", 0.0)),
                low=float(row.get("3. low", 0.0)),
                close=float(row.get("4. close", 0.0)),
                volume=0.0,
            )
        )
    return out
