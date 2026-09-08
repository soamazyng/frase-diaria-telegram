# 15 — /status completo

**What to build:** a usuária consegue diagnosticar o bot sozinha. `/status` responde, em horário local, o que aconteceu no último envio, quando é o próximo, em que estado está a diária de hoje, se a coleção veio do Notion ou do cache, e qual falha está ativa.

**Blocked by:** 11 — Snapshot durável, cache e fallback do Notion; 14 — Envio diário, retentativas e janela até 12:00.

**Status:** concluído em 2026-09-08 — ver `docs/15-status-completo.md`

- [x] `/status` passa pela mesma autenticação do webhook.
- [x] A resposta traz último envio confirmado, próxima ocorrência diária, situação da diária atual, última sincronização válida, última tentativa de sincronização, uso de cache e falhas ativas ou última falha.
- [x] A resposta distingue nunca enviado, cache desatualizado, falha, parcial e incerto (AC17).
- [x] Todos os horários são apresentados no fuso local da usuária (AC17).
- [x] Partes marcadas como incertas aparecem explicitamente, deixando claro que não serão reenviadas automaticamente.
- [x] `/status` não consome frase nem altera o ciclo.
- [x] A resposta não expõe tokens, URLs assinadas nem parâmetros de infraestrutura.
