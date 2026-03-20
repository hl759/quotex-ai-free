ALPHA HIVE AI - FIX DE STATS / ATIVOS / HORÁRIOS

Substitua estes arquivos:
- journal_manager.py
- result_evaluator.py

O que isso corrige:
- registra WIN/LOSS de forma compatível
- passa a alimentar Stats, Ativos e Horários
- salva o journal em /opt/render/project/src/data
- evita perder tudo por depender só de /tmp
