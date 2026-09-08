# 07 — Pedidos: identidades estáveis e máquina de estados

**What to build:** cada pedido passa a ter uma identidade estável e um estado explícito que sobrevive a reinícios. Reenviar o mesmo update do Telegram, ou reprocessar o mesmo dia, deixa de produzir uma segunda mensagem — o sistema reconhece que já viu aquele pedido e devolve o que já existe.

**Blocked by:** 06 — Seleção sem repetição e ciclos persistidos.

**Status:** concluído em 2026-09-07 — ver `docs/07-pedidos-identidades-e-estados.md`

- [x] Identidades implementadas: diária como conversa autorizada mais data local; extra como bot mais update_id; parte como pedido mais índice; tentativa como pedido mais número sequencial.
- [x] Repetir o evento diário, o webhook ou a recuperação do worker mantém a mesma identidade de pedido (AC02).
- [x] Instantes gravados em UTC; a chave diária é calculada pelo dia local.
- [x] Estados de pedido implementados com seus motivos de transição: pendente, reservado, enviando, aguardando tentativa, enviado, parcial, incerto, falhou, expirado.
- [x] Transições inválidas são rejeitadas; estados terminais não são reabertos por evento duplicado.
- [x] Cada tentativa fica registrada com instante, resultado, erro sanitizado, versão da aplicação e correlação.
- [x] Conteúdo extenso e históricos ficam em itens separados, sem item de crescimento ilimitado.
- [x] Índice de pendências permite buscar trabalho vencido sem varrer o histórico.
