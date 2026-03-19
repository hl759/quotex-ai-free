NEXUS v10.3 MAX FREE UPGRADE

Substitua os arquivos do projeto por estes arquivos.
Start Command no Render:
gunicorn --workers 1 --threads 1 --bind 0.0.0.0:$PORT app:app

Variáveis recomendadas:
TWELVE_API_KEY_1=
TWELVE_API_KEY_2=
FINNHUB_API_KEY=
ALPHA_VANTAGE_API_KEY=
SCAN_INTERVAL_SECONDS=60
TWELVE_DAILY_SOFT_LIMIT_PER_KEY=40
TWELVE_MINUTE_LIMIT_PER_KEY=1
TWELVE_GLOBAL_DAILY_HARD_STOP=60
CACHE_TTL_1MIN=58
CACHE_TTL_5MIN=295
ECONOMY_MODE_AFTER_TOTAL=30
FREEZE_TWELVE_AFTER_TOTAL=60
TWELVE_BATCH_SIZE=1
TWELVE_SCAN_INTERVAL_SECONDS=600
FINNHUB_PAUSE_SECONDS=120
ALPHA_PAUSE_SECONDS=180

Melhorias:
- consenso M1 + M5 sem custo extra
- regime de mercado
- filtro anti-lateral
- filtro “preço já andou demais”
- pausa temporária por sequência de losses
- bônus por ativo e por horário
- rigor dinâmico após perdas
- limite dinâmico de quantidade de sinais
- aba de melhores horários
- botão atualizar agora
