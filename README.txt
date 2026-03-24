V13 ETAPA 3 - BACKEND-ONLY

Arquivos:
- app.py
- capital_state.json

O que entra:
- lugar fixo para informar a banca real da IA
- leitura automática de capital_state.json no app.py
- integração automática com o Capital Mind Engine via indicators

Como usar:
1. Substitua o app.py pelo deste pacote.
2. Coloque capital_state.json no mesmo ambiente/estado usado pelo app.
3. Edite os campos:
   capital_current, capital_peak, daily_pnl, streak, daily_target_pct, daily_stop_pct

Observação:
- esta versão não remove nada existente
- apenas adiciona leitura automática da banca
