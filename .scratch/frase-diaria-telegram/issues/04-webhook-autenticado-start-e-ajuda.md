# 04 — Webhook autenticado, /start e ajuda

**What to build:** o bot passa a existir para a usuária: ela manda `/start` na conversa privada e recebe uma ajuda explicando `/frase` e `/status`. Qualquer outra origem — grupo, outro chat_id, segredo inválido — é rejeitada em silêncio, sem resposta e sem criar pedido.

**Blocked by:** 03 — Publicação manual em SAM: /health vivo na AWS.

**Status:** concluído em 2026-09-07 — ver `docs/04-webhook-telegram.md`

- [x] O webhook valida o cabeçalho de segredo do Telegram, o tipo de conversa privada e o chat_id autorizado, nessa ordem.
- [x] `/start` responde a ajuda de primeiro uso citando `/frase` e `/status`, sem consumir frase e sem alterar qualquer ciclo.
- [x] Comando desconhecido vindo da conversa autorizada responde ajuda curta.
- [x] Conversa de grupo, chat_id diferente e segredo inválido não produzem resposta nem pedido (AC18).
- [x] O update é persistido antes de a resposta HTTP confirmar recebimento.
- [x] Falha ao persistir devolve erro, para o Telegram reentregar.
- [x] Update repetido devolve sucesso reconhecendo o registro existente, sem criar segundo pedido.
- [x] Atualizações irrelevantes já validadas são reconhecidas e ignoradas.
- [x] Registro do webhook no Telegram documentado, com o segredo cadastrado fora do repositório.
