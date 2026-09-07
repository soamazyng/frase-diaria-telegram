# 05 — /frase entrega uma frase de fixture

**What to build:** a usuária manda `/frase` e recebe uma frase no Telegram. O conteúdo ainda vem de uma coleção de exemplo embutida, não do Notion — o objetivo é fechar o caminho completo comando → pedido persistido → worker → mensagem entregue, com a primeira frase real chegando no celular.

**Blocked by:** 04 — Webhook autenticado, /start e ajuda.

**Status:** ready-for-agent

- [ ] `/frase` cria um pedido extra persistido e tenta acordar o worker; a resposta HTTP não depende de trabalho em segundo plano.
- [ ] O worker processa pedidos lidos da persistência, não do corpo da requisição.
- [ ] Uma frase é tratada como entrega lógica e suas partes são salvas individualmente, com a confirmação de cada uma.
- [ ] Entrega confirmada exige sucesso do Telegram e persistência da confirmação.
- [ ] A frase entregue fica registrada no histórico com o conteúdo efetivamente enviado.
- [ ] Falha na chamada ao Telegram registra tentativa com erro sanitizado, sem token nem URL assinada nos logs.
