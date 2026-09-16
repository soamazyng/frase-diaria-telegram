# 29: Encapsular encerramento do pedido e avanço do ciclo

**What to build:** depois da tentativa de entrega, um módulo próprio transforma o resultado
tipado em estado persistido do pedido e na atualização correspondente do ciclo. Ele
concentra reagendamento, incerteza, falha definitiva, expiração, conclusão, liberação da
reserva, consumo normal ou com ressalva e retentativas por conflito concorrente. O
processamento do pedido permanece como coordenador de lease, preparação da frase e chamada
aos módulos profundos.

**Blocked by:** 28 — Extrair a entrega por destinatário para um módulo profundo.

**Status:** concluído em 2026-09-16 — ver `docs/29-encapsular-encerramento-e-ciclo.md`

- [x] O módulo de encerramento recebe um contexto tipado do pedido reservado e o resultado
      da entrega, escondendo do coordenador as combinações de estado final e mutação do ciclo.
- [x] A interface evita flags que escolhem comportamento; conclusão, falha, incerteza,
      expiração e ausência de conteúdo são representadas por operações ou tipos que revelam
      intenção.
- [x] A persistência mantém a ordem segura entre pedido e ciclo, de modo que uma interrupção
      não permita reenvio indevido nem deixe uma reserva sem referência.
- [x] Entrega completa consome a frase uma única vez; entrega parcial ou incerta consome com
      ressalva; falha comprovada sem envio libera a reserva.
- [x] Conflitos concorrentes na atualização do ciclo são relidos e reaplicados sem chamar o
      canal externo nem repetir uma entrega já realizada.
- [x] O processamento do pedido deixa de conter as regras de encerramento e retentativa do
      ciclo, mantendo apenas a coordenação do caso de uso e uma interface menor para seus
      colaboradores.
- [x] Os testes exercitam a interface pública do módulo extraído e o seam existente de
      processamento do pedido, sem testar métodos privados, demonstrando a preservação de
      AC03, AC04, AC13, AC14 e AC32–AC35.
- [x] A implementação segue `implement`, `python-clean-code`, `codebase-design` e TDD nos
      seams aprovados; testes focais, `make verificar` e `code-review` final nos eixos
      Standards e Spec passam sem achados impeditivos.
- [x] A entrega registra as skills, testes e reviews executados, atualiza a auditoria de
      tickets e é concluída em um commit exclusivo deste ticket.
