# Changelog resumido

## Refatoração broker-agnostic
- Remoção de qualquer dependência conceitual de corretoras
- Separação explícita de dados, features, especialistas, conselho, risco, auditoria e aprendizagem
- Criação de contratos tipados com `dataclasses`
- Criação de especialistas explícitos
- Criação de `council_engine`
- Transformação do `decision_engine` em orquestrador
- Refatoração do app Flask em rotas, serviços e assets estáticos
- Ampliação de auditoria, reputação por especialista e aprendizagem contextual
- Correção e simplificação do store persistente com suporte SQLite/Postgres
