# Render Free + PostgreSQL — operação segura

Este projeto agora trabalha em modo **zero-idle** por padrão para proteger o limite de banda do Render Free.

## Variáveis recomendadas no Render

```env
DATABASE_URL=postgresql://...
RUN_BACKGROUND_SCANNER=0
SCANNER_MAX_WORKERS=2
ASSETS_CRYPTO=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT
ASSETS_PURE_CRYPTO=
ASSETS_FOREX=EURUSD,GBPUSD,USDJPY,GBPJPY
ASSETS_METALS=
M1_OUTPUTSIZE=40
M5_OUTPUTSIZE=8
PG_POOL_MAX=3
```

## Como a memória fica no PostgreSQL

O `StateStore` usa PostgreSQL quando `DATABASE_URL` ou `ALPHA_HIVE_DATABASE_URL` está configurado. Ele persiste:

- runtime do scanner;
- sinais pendentes;
- histórico de resultado;
- aprendizado por segmento;
- reputação de especialistas;
- capital/configurações operacionais.

SQLite fica apenas como fallback local. No Render Free, não considere SQLite como memória permanente.

## Como reduzir quase a zero o consumo em idle

- `RUN_BACKGROUND_SCANNER=0` deixa o app sem thread autônoma.
- `GET /snapshot` deve ser leitura de estado, sem chamadas externas de mercado.
- `POST /atualizar` executa scan real sob demanda.
- A lista padrão de ativos foi reduzida para evitar payload duplicado.
- O scanner usa menos candles por ativo e libera cache após o ciclo.

## Quando usar scanner automático

Use `RUN_BACKGROUND_SCANNER=1` apenas se aceitar consumo contínuo de banda. No Render Free, o recomendado é deixar `0` e operar com scan sob demanda.

## Diagnóstico

Verifique `/diagnostics` ou endpoints de health para confirmar:

- backend do store = `postgres`;
- `postgres_configured=true`;
- sem fallback para SQLite;
- `loop_active=false` quando estiver em modo zero-idle.
