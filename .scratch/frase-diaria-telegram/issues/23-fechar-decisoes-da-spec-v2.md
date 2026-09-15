# 23 — Fechar decisões abertas da spec v2 e atualizar a spec v1

**What to build:** as decisões que a spec v2 (`.scratch/v2-telegram-bot.md`) deixou em
aberto ficam fechadas e registradas por escrito, e a spec v1
(`contextIA/Spec-Frase-Diaria-Telegram.md`) é atualizada para refletir que múltiplos
destinatários deixou de ser fora de escopo, dentro do limite decidido. Não há código
nesta entrega.

**Blocked by:** Nenhum — pode começar imediatamente.

**Status:** concluído em 2026-09-15 — ver `docs/23-fechar-decisoes-da-spec-v2.md`

- [x] Mecanismo de configuração dos destinatários autorizados decidido (um parâmetro SSM
      por destinatário vs. um único parâmetro com lista) e registrado na spec v2.
- [x] Limite máximo de destinatários decidido, ou explicitamente deixado sem limite
      numérico, com a razão registrada.
- [x] Texto final da seção "Fora de escopo" da spec v1 (seção 6) redigido, restringindo
      "múltiplos usuários" ao conjunto pequeno e fixo de destinatários, sem abrir a porta
      para grupos ou canais públicos.
- [x] Novos critérios de aceite formalizados a partir de AC32, cobrindo pelo menos: mesma
      frase para todos os destinatários; falha de entrega a um não afeta os outros;
      consumo único da frase no ciclo mesmo com vários destinatários; `/status` reportando
      a entrega de cada destinatário individualmente; segundo destinatário autenticado
      usando `/frase` e `/status`.
- [x] Vocabulário da spec v1 atualizado com o termo "destinatário" e a redefinição de
      "conversa autorizada" como plural.
- [x] Spec v2 (`.scratch/v2-telegram-bot.md`) atualizada para remover da seção "Further
      Notes" as decisões que deixaram de estar em aberto.