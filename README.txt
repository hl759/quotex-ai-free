CORREÇÃO DEFINITIVA DE CONFLUÊNCIA

Problema resolvido:
- a aba Sinais estava vazia enquanto a aba Decisão mostrava entrada forte

Causa:
- o signal_engine estava usando lógica separada e mais rígida que o decision_engine

Correção:
- agora a aba Sinais nasce do MESMO motor da aba Decisão
- se a Decisão mostrar entrada, a aba Sinais mostrará o mesmo ativo e mesma direção
- se a Decisão disser não operar, a aba Sinais fica vazia

Efeito:
- confluência total
- sem 'Base signal'
- sem contradição entre abas
- sem alterar app.py

Substitua apenas:
- signal_engine.py
