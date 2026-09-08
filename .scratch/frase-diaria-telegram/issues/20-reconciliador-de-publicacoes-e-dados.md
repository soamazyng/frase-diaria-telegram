# 20 — Reconciliador de publicações e compatibilidade de dados

**What to build:** os casos em que ninguém está lá para reagir. Se o runner morrer no meio de uma publicação, ou se o evento de fechamento do PR se perder, um workflow periódico percebe a divergência e age. E fica provado que publicar ou recuperar uma versão nunca custa o histórico.

**Blocked by:** 19 — Recuperação da versão anterior, caso a caso.

**Status:** concluído em 2026-09-08 — ver
`docs/20-reconciliador-de-publicacoes-e-dados.md`. Exercitado ao vivo após
o merge do PR #2: claim `sub` do OIDC confirmado contra token real, passo
de debug removido, caminho "implantação travada" exercitado sem
incidente. O caminho "reconciliar para a versão estável" revelou um
achado real (não corrigido nesta sessão, decisão explícita) — merge
commit gera um SHA nunca testado, o que fez o reconciliador abrir uma
issue e desabilitar de verdade o agendamento diário como falso positivo;
ambos revertidos na hora. Ver a seção "Próximo passo" do documento para a
correção pendente antes do ticket 21.

- [x] Um workflow periódico **de hora em hora** consulta o manifesto de publicação e o estado do PR, cobrindo runner interrompido e falha do evento de fechamento. *(implementado; só roda de verdade depois do merge para `main` — ver nota de status)*
- [x] O reconciliador adquire a mesma exclusão mútua de produção antes de agir, e reconsulta o estado após esperar. *(mesmo `concurrency: group: producao-frase-diaria` dos tickets 18/19)*
- [x] Uma publicação registrada como "em andamento" há tempo demais é reconciliada em vez de ficar travando o grupo indefinidamente. *(limite de 20min, marca `error` na API de Deployments)*
- [x] Deploys, rollback e fechamento de PR concorrentes não sobrescrevem uma versão mais recente por evento obsoleto (AC23). *(garantido pela exclusão mútua + reconsulta de PR/versão ativa dentro da trava, mesmo padrão do AC22 dos tickets 18/19)*
- [x] Atualização e recuperação preservam histórico e compatibilidade dos dados (AC26). *(garantido pela separação de stacks já existente desde o ticket 03 — a stack de aplicação nunca importa nem exporta nada que permita tocar a stack de dados; nenhuma lógica nova neste ticket mexe em dados)*
- [x] Mudanças de dados são aditivas e legíveis pela versão anterior; nenhuma migração destrutiva entra no MVP. *(nenhuma migração de dados existe neste ticket nem em nenhum anterior — invariante arquitetural a respeitar em tickets futuros que toquem dados, não algo a implementar aqui)*
- [x] O histórico não volta no tempo e mensagens já enviadas permanecem no Telegram, mesmo após recuperação. *(republicar código nunca toca o DynamoDB nem desfaz envios; consequência direta de a recuperação/reconciliação só trocar o artefato deployado)*
- [x] O custo da execução periódica entra na estimativa registrada no ticket 01 (`docs/01-custo-e-elegibilidade.md`, seção 4).
