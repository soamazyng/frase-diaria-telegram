# 24 — Autorização e comandos reconhecem múltiplos destinatários

**What to build:** `/frase`, `/status` e `/start` funcionam para qualquer destinatário
dentro do conjunto autorizado, não só para um único chat_id fixo. Uma conversa fora do
conjunto continua sendo recusada silenciosamente, sem resposta e sem pedido — o mesmo
comportamento de hoje, estendido de um chat_id para um conjunto.

**Blocked by:** 23 — Fechar decisões abertas da spec v2 e atualizar a spec v1.

**Status:** ready-for-agent — indicação documental, sem label aplicada a um rastreador.

- [ ] `PoliticaDeAcesso` passa a aceitar um conjunto de chat_ids autorizados, mantendo a
      ordem de verificação (segredo antes de conversa) e `hmac.compare_digest` no segredo.
- [ ] Novo(s) parâmetro(s) SSM, no formato decidido no ticket 23, alimentam o conjunto de
      destinatários autorizados na composição da aplicação.
- [ ] Confirmado — não presumido — que nenhuma mudança de política IAM é necessária, já
      que a permissão existente cobre o prefixo `/frase-diaria/*` inteiro.
- [ ] Dois chat_ids de fixture, ambos autorizados, cada um pedindo `/frase`, recebem cada
      um o próprio pedido extra, com identidades distintas.
- [ ] `/status` responde a qualquer destinatário autorizado.
- [ ] Um chat_id fora do conjunto continua sem resposta e sem pedido criado (equivalente
      ao comportamento do AC18 hoje, estendido para um conjunto de autorizados).
- [ ] Conversa de grupo continua recusada, independentemente do chat_id.
- [ ] Testes cobrindo aceitação dos dois destinatários configurados e recusa de um
      terceiro chat_id e de uma conversa de grupo.