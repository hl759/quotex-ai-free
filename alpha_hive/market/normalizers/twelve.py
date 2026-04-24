from __future__ import annotations

from typing import Dict, List

from alpha_hive.core.contracts import Candle


def normalize(values: List[Dict[str, str]]) -> List[Candle]:
    """Converte resposta do Twelve Data para lista de Candle (oldest-to-newest).

    A API do Twelve Data retorna em ordem DESCENDENTE (values[0] = mais recente).
    O reversal ao final corrige para oldest-to-newest, necessário para os indicadores.
    """
    out: List[Candle] = []
    for row in values:
        try:
            out.append(
                Candle(
                    ts=row.get("datetime", ""),
                    open=float(row.get("open", 0.0)),
                    high=float(row.get("high", 0.0)),
                    low=float(row.get("low", 0.0)),
                    close=float(row.get("close", 0.0)),
                    volume=float(row.get("volume", 0.0) or 0.0),
                )
            )
        except Exception:
            continue
    out.reverse()  # API retorna newest-first; invertemos para oldest-first
    return out
