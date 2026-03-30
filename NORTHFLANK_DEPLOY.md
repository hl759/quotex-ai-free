# Alpha Hive AI - Deploy na Northflank

## O que subir
Use este diretório/ZIP em um serviço **Web** na Northflank usando o **Dockerfile** incluído.

## Passos rápidos
1. Crie uma conta/organização na Northflank.
2. Adicione um método de pagamento (a Northflank exige isso mesmo no Sandbox gratuito).
3. Crie um **Project**.
4. Crie um **Service** do tipo **Deployment Service**.
5. Escolha deploy por **Git** ou **Upload** e use este código.
6. Mantenha a porta HTTP em `8080`.
7. Health check: `/ping`
8. Start command: já vem do `Dockerfile`, não precisa alterar.

## Variáveis de ambiente recomendadas
- `PORT=8080`
- `PYTHONUNBUFFERED=1`
- `ALPHA_HIVE_MODE=validation`

### Se for usar Neon/Postgres
- `DATABASE_URL=postgresql://...`

## Observações
- Não suba `alpha_hive_data/` para não levar SQLite local/estado antigo junto.
- Primeiro teste sem `DATABASE_URL` para validar interface e scanner.
- Depois ligue o banco externo.
