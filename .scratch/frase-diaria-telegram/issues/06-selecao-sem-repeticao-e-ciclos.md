# 06 — Seleção sem repetição e ciclos persistidos

**What to build:** chamar `/frase` várias vezes passa a percorrer a coleção inteira sem repetir. Ao esgotar, abre-se um ciclo novo que não começa pela frase que acabou de sair. O estado do ciclo sobrevive a reinícios da aplicação.

**Blocked by:** 05 — /frase entrega uma frase de fixture.

**Status:** concluído em 2026-09-07 — ver `docs/06-ciclos-e-selecao.md`

- [x] A seleção sorteia entre frases ativas ainda não consumidas nem reservadas no ciclo.
- [x] Com coleção estável de N frases, N entregas no ciclo têm identidades distintas (AC04).
- [x] Um novo ciclo abre quando todas as ativas foram consumidas e não há reservas pendentes.
- [x] Com duas ou mais frases ativas, a primeira do novo ciclo difere da última entregue; com uma, a repetição é permitida; com zero, registra ausência de conteúdo (AC05).
- [x] O estado de consumo é guardado por identidade de frase e sobrevive a reinício.
- [x] Consumo é marcado somente após entrega completa confirmada.
- [x] Uma falha comprovada sem nenhum envio libera a reserva ao encerrar o pedido.
- [x] Entrega parcial ou incerta mantém a frase marcada como utilizada com ressalva naquele ciclo.
