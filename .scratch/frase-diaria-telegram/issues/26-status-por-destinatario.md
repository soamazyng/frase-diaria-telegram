# 26 — `/status` reporta a entrega do próprio destinatário

**What to build:** cada destinatário que consulta `/status` vê o resultado da própria
entrega do dia (confirmada, incerta, falha ou parcial), não um agregado que misture a
situação dele com a de outro destinatário.

**Blocked by:** 25 — Diária com múltiplos destinatários: entrega compartilhada e falhas
independentes.

**Status:** concluído em 2026-09-16 — ver `docs/26-status-por-destinatario.md`

- [x] `ConsultarStatus` / `RelatorioDeStatus` derivam a situação da diária de hoje a
      partir das partes confirmadas/incertas do destinatário que perguntou, não do
      estado agregado do pedido.
- [x] Dois destinatários com desfechos diferentes na mesma diária (um confirmado, outro
      incerto) recebem respostas de `/status` diferentes entre si.
- [x] `/status` continua sem consumir frase, sem alterar o ciclo e sem expor tokens,
      URLs assinadas ou parâmetros de infraestrutura.
- [x] Horários continuam apresentados no fuso local (AC17 mantido).
