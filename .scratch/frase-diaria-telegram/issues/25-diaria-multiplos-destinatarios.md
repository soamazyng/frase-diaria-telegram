# 25 — Diária com múltiplos destinatários: entrega compartilhada e falhas independentes

**What to build:** o pedido diário passa a carregar todos os destinatários autorizados;
uma única frase é sorteada, reservada e consumida no ciclo; a mesma frase é entregue a
cada destinatário de forma independente — uma falha permanente de entrega a um
destinatário não impede nem atrasa a entrega aos demais, e não trava o pedido inteiro.

**Blocked by:** 24 — Autorização e comandos reconhecem múltiplos destinatários.

**Status:** concluído em 2026-09-15 — ver `docs/25-diaria-multiplos-destinatarios.md`

- [x] `Pedido.chat_id` (destinatário único) dá lugar a `Pedido.destinatarios` (um ou
      mais); um extra continua com exatamente um destinatário — quem pediu.
- [x] Identidade da diária deixa de incluir o chat_id (`diaria#<dia>` em vez de
      `diaria#<chat_id>#<dia>`); identidades antigas permanecem legíveis como histórico,
      sem serem reprocessadas.
- [x] Reserva e consumo de frase no ciclo continuam acontecendo uma única vez por pedido,
      independentemente do número de destinatários — sem duplicar consumo nem criar
      reserva órfã.
- [x] Rastreio de partes (confirmada / incerta / intenção registrada) passa a ser por
      destinatário, não só por índice — cada combinação destinatário+parte tem seu
      próprio desfecho.
- [x] Pedidos persistidos no formato anterior (um único `chat_id`, sem `destinatarios`)
      continuam sendo lidos corretamente, no mesmo padrão de compatibilidade já usado
      para `bot_legado` / `estado_legado`.
- [x] Teste do caminho feliz: dois destinatários de fixture recebem texto idêntico a
      partir de um único sorteio; o ciclo avança (consome) uma única vez.
- [x] Teste que quebra a invariante de propósito: um `ErroDoTelegram` permanente simulado
      para um destinatário não impede a entrega ao outro, e o pedido não fica preso nem
      gera reserva órfã no ciclo.
- [x] Estado agregado do pedido (`ENVIADO` / `PARCIAL` / `INCERTO` / `FALHOU`) reflete
      corretamente o pior caso entre os destinatários.