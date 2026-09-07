# 13 — Imagens com cache durável

**What to build:** frases com imagem passam a chegar com a imagem. Como as URLs do Notion expiram, o bot guarda uma cópia privada durável e reaproveita o identificador de arquivo do Telegram, de modo que uma frase antiga continue entregável meses depois.

**Blocked by:** 11 — Snapshot durável, cache e fallback do Notion; 12 — Renderização rica e divisão de mensagens.

**Status:** ready-for-agent

- [ ] Imagens existentes na frase são entregues; nenhuma imagem, card ou ilustração é gerada.
- [ ] Cache privado de imagens é mantido em bucket próprio e referenciado na persistência.
- [ ] O identificador de arquivo devolvido pelo Telegram é reutilizado quando disponível.
- [ ] Imagem cuja URL de origem expirou ainda é enviada a partir do cache durável (AC12).
- [ ] Mídia que não pôde ser preservada registra falha ou entrega parcial; texto sem imagem nunca é classificado silenciosamente como entrega completa (AC12).
- [ ] Todas as partes e suas confirmações ficam salvas, inclusive as de mídia.
- [ ] O custo do bucket e das requisições entra na estimativa registrada no ticket 01.
