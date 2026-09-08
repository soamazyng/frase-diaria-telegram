# 19 — Recuperação da versão anterior, caso a caso

**What to build:** quando uma publicação falha ou um PR é abandonado, o serviço volta sozinho para uma versão que funciona — sem reconstruir dependências, sem perder histórico e sem que um evento atrasado sobrescreva uma publicação mais recente.

**Blocked by:** 18 — Pipeline vinculado ao SHA e publicação serializada.

**Status:** implementado e exercitado ao vivo em 2026-09-08 — ver
`docs/19-recuperacao-da-versao-anterior.md`. Cobertos: falha de deploy e
falha de diagnóstico (recuperação síncrona, no mesmo job `publicar`). Fora
do escopo desta entrega: recuperação de PR fechado sem merge (AC25) — exige
decisão de segurança própria sobre a trust policy OIDC para eventos
`pull_request`, documentada como próximo passo.

**Dois testes de fogo reais executados** (quebrar o diagnóstico de
propósito, a pedido da usuária). O primeiro achou e corrigiu um bug real:
os passos de recuperação tinham `if:` sem `always()`, e o `success()`
implícito do GitHub Actions os bloqueava depois de uma falha anterior no
job — a recuperação nunca chegou a rodar, e a cadeia caiu direto em
desabilitar o agendamento diário de verdade (corrigido na hora, agendamento
reabilitado e conferido `ENABLED`). O segundo, já com o bug corrigido,
provou a cadeia completa de ponta a ponta contra AWS/GitHub reais:
diagnóstico reprova → última publicação saudável localizada → artefato
baixado e republicado sem reconstruir → diagnóstico pós-recuperação aprova
→ implantação de recuperação registrada `success` → agendamento nunca
tocado (a recuperação funcionou). Detalhes completos em `docs/19`.

- [x] Artefatos imutáveis, configuração e manifesto suficientes para restaurar uma publicação sem reconstruir dependências ficam preservados. *(retenção do artefato: 1 → 14 dias)*
- [x] Dois marcos são mantidos e consultáveis: a publicação saudável anterior à tentativa e a versão estável aceita em `main`. *(API de Deployments do ticket 18 + HEAD de `main`; sem manifesto novo)*
- [x] Falha de deploy recupera a publicação saudável anterior à tentativa, considerando também o rollback nativo da infraestrutura (AC24). *(mesmo caminho de código da falha de diagnóstico abaixo; caminho "desabilitar" exercitado ao vivo na 1ª rodada)*
- [x] Falha do diagnóstico pós-publicação recupera a publicação saudável anterior à tentativa (AC24). *(exercitado de ponta a ponta em duas rodadas reais: achou e corrigiu um bug de always() na 1ª, provou o redeploy completo — localizar, baixar, checksum, sam deploy, verificar — na 2ª)*
- [ ] Fechamento de PR sem merge, após várias candidatas, restaura a versão estável anterior ao PR — e não uma candidata do mesmo PR (AC25). *(fora do escopo desta entrega — ver docs/19, "Próximo passo")*
- [x] Primeiro deploy sem versão anterior reverte os recursos de aplicação possíveis, deixa os envios desabilitados, preserva os dados já criados e documenta a ausência de versão recuperável (AC24). *(detectado quando a busca por implantação `success` anterior não acha nada; desabilita agendamento + abre issue)*
- [x] Antes de recuperar, confere-se se a publicação ativa ainda pertence à tentativa ou ao PR afetado; um evento antigo não sobrescreve uma publicação posterior (AC23). *(garantido pela exclusão mútua do job — a recuperação roda dentro da mesma trava da tentativa original, nenhum evento concorrente pode intercalar)*
- [x] Repetir o evento de recuperação é idempotente. *(a busca sempre parte da API de Deployments real; repetir a mesma falha encontra a mesma última implantação `success`)*
- [x] A recuperação usa o mesmo grupo de exclusão mútua da publicação, com verificação de atualidade **após** esperar — sem presumir ordem de chegada dos jobs. *(mesmo job, mesma trava `producao-frase-diaria`)*
- [x] A versão restaurada é verificada e o resultado é guardado; falhando, o merge continua bloqueado, o diagnóstico é registrado no GitHub e um procedimento manual com o último artefato válido fica disponível.
- [x] Novos envios são desabilitados quando não houver versão operacional verificável. *(decisão da usuária: só infra — desliga o ScheduleV2 da diária via scheduler:UpdateSchedule)*
