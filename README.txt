V13 ETAPA 9 - BACKEND-ONLY

Substitua estes arquivos:
- veteran_discernment_layer.py
- decision_engine.py

O que entra:
- julgamento de qualidade final: premium, bom, aceitável, duvidoso, vetado
- anti-pattern memory (memória de armadilhas recorrentes)
- hierarquia de contexto sobre setup
- veto inteligente mesmo com score alto
- integrado ao decision_engine como camada final
- aprendizado com histórico via journal_manager
- sem alterar app.py
- sem remover nada existente
