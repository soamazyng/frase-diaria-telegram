# 20 — Reconciliador de publicações e compatibilidade de dados

**What to build:** os casos em que ninguém está lá para reagir. Se o runner morrer no meio de uma publicação, ou se o evento de fechamento do PR se perder, um workflow periódico percebe a divergência e age. E fica provado que publicar ou recuperar uma versão nunca custa o histórico.

**Blocked by:** 19 — Recuperação da versão anterior, caso a caso.

**Status:** ready-for-agent

- [ ] Um workflow periódico consulta o manifesto de publicação e o estado do PR, cobrindo runner interrompido e falha do evento de fechamento.
- [ ] O reconciliador adquire a mesma exclusão mútua de produção antes de agir, e reconsulta o estado após esperar.
- [ ] Uma publicação registrada como "em andamento" há tempo demais é reconciliada em vez de ficar travando o grupo indefinidamente.
- [ ] Deploys, rollback e fechamento de PR concorrentes não sobrescrevem uma versão mais recente por evento obsoleto (AC23).
- [ ] Atualização e recuperação preservam histórico e compatibilidade dos dados (AC26).
- [ ] Mudanças de dados são aditivas e legíveis pela versão anterior; nenhuma migração destrutiva entra no MVP.
- [ ] O histórico não volta no tempo e mensagens já enviadas permanecem no Telegram, mesmo após recuperação.
- [ ] O custo da execução periódica entra na estimativa registrada no ticket 01.
