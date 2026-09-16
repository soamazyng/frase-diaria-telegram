# 28: Extrair a entrega por destinatário para um módulo profundo

**What to build:** a entrega de uma frase passa a ser realizada por um módulo próprio,
injetado no processamento do pedido. Esse módulo concentra o envio de cada parte a cada
destinatário, o registro de intenção, confirmação ou incerteza, a classificação de falhas
e o cálculo de retentativa. O processamento continua apresentando exatamente os mesmos
resultados observáveis, mas deixa de conhecer os detalhes do canal de envio.

**Blocked by:** None (can start immediately).

**Status:** concluído em 2026-09-16 — ver `docs/28-extrair-entrega-por-destinatario.md`

- [x] O módulo de entrega expõe uma interface pequena que recebe o pedido, a frase e o
      sequencial da tentativa e devolve um resultado tipado com desfecho agregado, motivo,
      próxima tentativa quando aplicável e indicação de entrega confirmada.
- [x] O módulo recebe suas dependências na composição; o processamento do pedido não cria
      internamente o adaptador nem recebe diretamente o canal externo.
- [x] A composição e todos os consumidores do contrato interno atualizado são migrados sem
      manter uma camada temporária de compatibilidade.
- [x] Intenção antes do envio, confirmação por parte, suspensão de reenvio ambíguo, retomada
      apenas das partes pendentes e isolamento entre destinatários permanecem preservados.
- [x] Falha permanente de um destinatário não impede a tentativa aos demais e o resultado
      agregado mantém todos os motivos relevantes.
- [x] Erros transitórios respeitam `retry_after`, backoff com teto e o prazo do pedido sem
      autorizar reenvio cego.
- [x] Os testes exercitam a interface pública do novo módulo e o seam existente de
      processamento do pedido, sem acoplamento a métodos privados, demonstrando a
      preservação de AC03, AC13, AC14 e AC32–AC35.
- [x] A implementação segue `implement`, `python-clean-code`, `codebase-design` e TDD nos
      seams aprovados; testes focais, `make verificar` e `code-review` final nos eixos
      Standards e Spec passam sem achados impeditivos.
- [x] A entrega registra as skills, testes e reviews executados, atualiza a auditoria de
      tickets e é concluída em um commit exclusivo deste ticket.
