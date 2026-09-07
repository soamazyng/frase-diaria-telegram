# 11 — Snapshot durável, cache e fallback do Notion

**What to build:** o resultado da sincronização passa a ser persistido, e o bot continua entregando frases quando o Notion está fora do ar. Inserções, edições e exclusões na coleção passam a se refletir corretamente no ciclo em andamento.

**Blocked by:** 09 — Lease, escritas condicionais e concorrência; 10 — Sincronização com Notion substitui as fixtures.

**Status:** ready-for-agent

- [ ] Snapshot persistido com identificador, instante, resultado de validação, quantidade e referência ao snapshot ativo.
- [ ] A sincronização acontece antes de cada pedido diário ou extra, e novamente antes de uma nova tentativa que vá enviar conteúdo.
- [ ] Notion indisponível usa a última coleção válida e indica uso de cache, data e erro da sincronização; sem cache disponível, registra falha (AC09).
- [ ] Leitura completa sem frases substitui a coleção por um snapshot vazio, registra "coleção vazia" e não ressuscita itens excluídos (AC09).
- [ ] Inserção entra no ciclo atual; edição mantém identidade e a marca de consumo; exclusão remove a elegibilidade preservando o histórico (AC07).
- [ ] Numa tentativa sem nenhuma parte enviada, o conteúdo da frase reservada é atualizado; se a frase foi excluída, a reserva é liberada e outra elegível é selecionada.
- [ ] Após entrega parcial, a versão iniciada é mantida para concluir as partes restantes, registrando eventual alteração da fonte.
- [ ] O conteúdo efetivamente enviado permanece no histórico mesmo depois de a origem mudar.
