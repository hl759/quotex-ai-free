from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from alpha_hive.core.contracts import Candle


def normalize(data: Dict[str, list]) -> List[Candle]:
    """Converte resposta do Finnhub para lista de Candle (oldest-to-newest).

    A API do Finnhub retorna candles em ordem ASCENDENTE (index 0 = mais antigo).
    """
    if data.get("s") != "ok" or not data.get("c"):
        return []
    out: List[Candle] = []
    timestamps = data.get("t", [])
    opens = data.get("o", [])
    highs = data.get("h", [])
    lows = data.get("l", [])
    closes = data.get("c", [])
    volumes = data.get("v", [])
    for i in range(len(closes)):
        try:
            out.append(
                Candle(
                    ts=datetime.utcfromtimestamp(timestamps[i]).strftime("%Y-%m-%d %H:%M:%S"),
                    open=float(opens[i]),
                    high=float(highs[i]),
                    low=float(lows[i]),
                    close=float(closes[i]),
                    volume=float(volumes[i]) if i < len(volumes) else 0.0,
                )
            )
        except Exception:
            continue
    # Sem reversal: Finnhub retorna ascendente (oldest first) → ordem já correta
    return out
