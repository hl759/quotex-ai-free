# ⚡ Quotex AI Signals — Versão Gratuita

Sistema de sinais para opções binárias com dados reais de Forex e Cripto.
100% gratuito, roda no celular.

---

## PASSO 1 — Pegar sua chave da Twelve Data (grátis)

1. Acesse **twelvedata.com**
2. Clique em **Get your free API key**
3. Crie uma conta gratuita
4. Copie sua API key (parece com: `abc123def456...`)

---

## PASSO 2 — Colocar os arquivos no GitHub

1. Acesse **github.com** e faça login
2. Crie um repositório novo chamado `quotex-ai-free`
3. Faça upload de TODOS os arquivos desta pasta
4. Confirme o upload

---

## PASSO 3 — Hospedar no Render.com (grátis)

1. Acesse **render.com**
2. Clique em **New +** → **Web Service**
3. Conecte seu GitHub e escolha `quotex-ai-free`
4. Preencha assim:
   - **Name:** quotex-ai-signals
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 1`
5. Em **Environment Variables** adicione:
   - Key: `TWELVE_DATA_KEY`
   - Value: (sua chave da Twelve Data)
6. Clique em **Create Web Service**
7. Aguarde 3-5 minutos
8. Render vai te dar um link como: `https://quotex-ai-signals.onrender.com`

---

## PASSO 4 — Manter o servidor sempre acordado (GRÁTIS)

O Render gratuito "dorme" após 15 minutos. Para evitar isso:

1. Acesse **uptimerobot.com**
2. Crie uma conta gratuita
3. Clique em **Add New Monitor**
4. Tipo: **HTTP(s)**
5. URL: `https://SEU-LINK.onrender.com/ping`
6. Intervalo: **5 minutes**
7. Salve

✅ Pronto! O UptimeRobot vai pingar seu servidor a cada 5 minutos,
mantendo ele sempre acordado — completamente grátis!

---

## Ativos monitorados

### Forex
- EUR/USD · GBP/USD · USD/JPY · AUD/USD
- USD/CAD · GBP/JPY · EUR/GBP · EUR/JPY

### Cripto
- BTC/USD · ETH/USD · LTC/USD

---

## Como usar

1. Abra o link do seu app no celular
2. Aguarde o primeiro scan (pode levar 2-3 minutos)
3. Quando aparecer um sinal, abra o trade no Quotex
4. Após expirar, toque em ✓ WIN ou ✗ LOSS para registrar
5. O sistema aprende com seus resultados

---

## Sinais são gerados quando:

✓ M1 e M5 mostram a mesma tendência
✓ EMA 9, 21 e 50 alinhadas
✓ Padrão de candle confirmado
✓ RSI em zona de reversão
✓ MACD alinhado
✓ Score de confluência ≥ 6.5/9

---

## Suporte

Qualquer dúvida, volte ao Claude e pergunte!
