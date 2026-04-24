from __future__ import annotations

from typing import Dict, List

from alpha_hive.core.contracts import Candle


def normalize(data: Dict[str, dict]) -> List[Candle]:
    """Converte resposta do Alpha Vantage FX_INTRADAY para lista de Candle (oldest-to-newest).

    A API retorna em ordem DESCENDENTE (chave mais recente primeiro no dict).
    O reversal ao final corrige para oldest-to-newest, necessário para os indicadores.
    O limite de 50 itens foi removido — o caller controla outputsize via parâmetro da API.
    """
    series = data.get("Time Series FX (1min)", {})
    out: List[Candle] = []
    for dt_str, row in series.items():
        try:
            out.append(
                Candle(
                    ts=dt_str,
                    open=float(row.get("1. open", 0.0)),
                    high=float(row.get("2. high", 0.0)),
                    low=float(row.get("3. low", 0.0)),
                    close=float(row.get("4. close", 0.0)),
                    volume=0.0,  # FX_INTRADAY não fornece volume
                )
            )
        except Exception:
            continue
    out.reverse()  # API retorna newest-first; invertemos para oldest-first
    return out
