# 22 — Documentação de operação e aceite real controlado

**What to build:** o fechamento do MVP. A usuária consegue configurar credenciais, diagnosticar uma falha e executar uma recuperação seguindo a documentação, e o sistema inteiro é exercitado uma vez de ponta a ponta contra a AWS real — inclusive uma entrega de verdade e uma recuperação controlada.

**Blocked by:** 13 — Imagens com cache durável; 15 — /status completo; 21 — Proteção de main e merge manual.

**Status:** ready-for-agent

- [ ] Documentação de operação permite configurar credenciais, diagnosticar falha e executar recuperação (AC30).
- [ ] Aceite na AWS inclui uma entrega diária real autorizada, `/frase` e `/status` exercitados na conversa privada.
- [ ] Persistência entre versões verificada: publicar uma nova versão não perde histórico nem estado de ciclo (AC26).
- [ ] Uma recuperação é exercitada de forma controlada e o resultado é registrado.
- [ ] Nenhum ambiente permanente de dev é criado.
- [ ] Estimativa de consumo do ticket 01 revisada contra o consumo real observado.
- [ ] Limitações remanescentes registradas explicitamente, incluindo a ausência de garantia de entrega exatamente uma vez sob falha externa ambígua.
- [ ] Após duas semanas de uso, a avaliação pessoal das duas frases de valor é feita, sem coleta automática (AC31).
