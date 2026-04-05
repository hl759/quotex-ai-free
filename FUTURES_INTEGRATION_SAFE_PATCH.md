Integração segura de Binance Futures sobre a base real do projeto.

Arquivos novos:
- futures_module.py
- self_optimization_engine.py
- binance_runtime_vault.py
- binance_broker_service.py
- futures_bot_service.py

Arquivos alterados:
- app.py
- scanner.py

Pontos principais:
- Binárias continuam como fluxo principal e manual-only.
- Futures entra como camada opcional; se algum módulo futures faltar, o app não cai.
- Credenciais da Binance ficam no backend; o painel só envia para memória da instância.
- O scanner ganhou suporte a timeframe e lista de ativos sem quebrar scan_assets legado.
- O bootstrap do snapshot foi preservado para evitar UI vazia na subida.

Rotas novas:
- /futures/status
- /futures/connect
- /futures/disconnect
- /futures/account
- /futures/positions
- /futures/orders
- /futures/analyze
- /futures/execute
- /futures/bot/start
- /futures/bot/stop
- /futures/bot/status

Recomendação de deploy inicial:
- BINANCE_FUTURES_AUTO_EXECUTION=0
- BINANCE_FUTURES_EXECUTION_MODE=paper
- BINANCE_FUTURES_TESTNET=1

Observação:
- Adicione .gitignore para não versionar alpha_hive_state.db, futures_bot_state.json, alpha_hive_data e __pycache__.
