# Alpha Hive AI

Infraestrutura broker-agnostic de decisão operacional para trading, baseada em conselho de especialistas, governança de risco, aprendizagem contínua e auditoria estatística.

## O que este projeto faz
- Coleta dados multi-fonte de mercado
- Normaliza candles e qualifica confiabilidade do feed
- Extrai features contextuais
- Faz votação por especialistas
- Consolida consenso ponderado por reputação contextual
- Aplica governança de risco antes da liberação operacional
- Registra resultados, edge, especialistas e segmentos
- Mantém endpoints HTTP para monitoramento e operação assistida

## O que este projeto não faz
- Não conecta corretoras
- Não executa ordens
- Não depende de login em broker
- Não assume lucro universal em qualquer ambiente

## Estrutura
O projeto foi organizado em:
- `alpha_hive/app`
- `alpha_hive/market`
- `alpha_hive/specialists`
- `alpha_hive/council`
- `alpha_hive/intelligence`
- `alpha_hive/risk`
- `alpha_hive/learning`
- `alpha_hive/audit`
- `alpha_hive/services`
- `alpha_hive/storage`

## Executar localmente
```bash
pip install -r requirements.txt
python app.py
```

## Testes
```bash
pytest -q
```
