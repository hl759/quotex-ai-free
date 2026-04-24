from __future__ import annotations

import time
from datetime import datetime
from typing import List

from alpha_hive.core.contracts import Candle


def normalize(rows: List[list]) -> List[Candle]:
    """Converte resposta da Binance klines para lista de Candle (oldest-to-newest).

    A API da Binance retorna klines em ordem ASCENDENTE (index 0 = mais antigo).
    O último elemento é o candle AINDA EM FORMAÇÃO (closeTime no futuro).
    Esse candle é descartado para que a análise use somente barras fechadas.
    """
    now_ms = time.time() * 1000
    out: List[Candle] = []
    for row in rows:
        try:
            # row[6] = closeTime em milissegundos; candle em formação tem closeTime > now
            close_time_ms = float(row[6]) if len(row) > 6 else 0.0
            if close_time_ms > now_ms:
                continue  # candle ainda não fechou — descartar
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
        except Exception:
            continue
    # Sem reversal: Binance retorna ascendente (oldest first) → ordem já correta
    return out
