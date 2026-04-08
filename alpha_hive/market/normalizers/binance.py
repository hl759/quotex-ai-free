from __future__ import annotations

from datetime import datetime
from typing import List

from alpha_hive.core.contracts import Candle

def normalize(rows: List[list]) -> List[Candle]:
    out: List[Candle] = []
    for row in rows:
        out.append(
            Candle(
                ts=datetime.utcfromtimestamp(row[0] / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    out.reverse()
    return out
