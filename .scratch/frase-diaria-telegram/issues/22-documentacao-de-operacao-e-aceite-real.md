# 22 — Documentação de operação e aceite real controlado

**What to build:** o fechamento do MVP. A usuária consegue configurar credenciais, diagnosticar uma falha e executar uma recuperação seguindo a documentação, e o sistema inteiro é exercitado uma vez de ponta a ponta contra a AWS real — inclusive uma entrega de verdade e uma recuperação controlada.

**Blocked by:** 15 — /status completo; 21 — Proteção de main e merge manual.

**Status:** em andamento em 2026-09-11 — só falta o item de tempo (AC31),
ver `docs/22-documentacao-de-operacao-e-aceite-real.md`. `/frase` e
`/status` exercitados de verdade na conversa privada, e a entrega diária
agendada confirmada em uso normal pela usuária.

- [x] Documentação de operação permite configurar credenciais, diagnosticar falha e executar recuperação (AC30). *(runbook consolidado em `docs/22`, referenciando as fontes já existentes)*
- [x] Aceite na AWS inclui uma entrega diária real autorizada, `/frase` e `/status` exercitados na conversa privada. *(`/frase`/`/status` autorizados e exercitados de verdade contra o webhook real, usuária confirmou recebimento de ambos, uma única vez cada — achado real registrado: `/frase` foi classificado internamente como "incerto" mas entregou corretamente, exercitando a limitação já documentada de entrega sem garantia exatamente-uma-vez. Entrega diária agendada confirmada pela usuária em uso normal: "diariamente eu já estou recebendo as mensagens, está tudo ok".)*
- [x] Persistência entre versões verificada: publicar uma nova versão não perde histórico nem estado de ciclo (AC26). *(verificado ao vivo, read-only — tabela sobreviveu a dezenas de republicações dos tickets 18–21; achado real de drift em `DeletionProtectionEnabled`, ver docs/22)*
- [x] Uma recuperação é exercitada de forma controlada e o resultado é registrado. *(já satisfeito pelos testes de fogo reais do ticket 19 e pelo exercício real do reconciliador no ticket 20 — não repetido, apenas referenciado)*
- [x] Nenhum ambiente permanente de dev é criado. *(confirmado ao vivo: só as 3 stacks do projeto existem na conta)*
- [x] Estimativa de consumo do ticket 01 revisada contra o consumo real observado. *(consulta ao vivo à conta AWS e ao GitHub — dentro ou melhor que o estimado em todos os itens, ver docs/22)*
- [x] Limitações remanescentes registradas explicitamente, incluindo a ausência de garantia de entrega exatamente uma vez sob falha externa ambígua. *(seção dedicada em docs/22)*
- [ ] Após duas semanas de uso, a avaliação pessoal das duas frases de valor é feita, sem coleta automática (AC31). *(não pode ser satisfeito agora por definição — precisa do tempo real passar)*
