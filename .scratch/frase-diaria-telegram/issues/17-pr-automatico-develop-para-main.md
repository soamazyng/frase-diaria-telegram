# 17 — PR automático develop → main

**What to build:** a desenvolvedora deixa de abrir PR na mão. Todo push em `develop` que tenha diferenças para `main` garante que exista um PR aberto entre as duas, e os pushes seguintes continuam no mesmo PR para concentrar a revisão.

**Blocked by:** 16 — Bootstrap OIDC AWS e base do GitHub.

**Status:** ready-for-agent

- [ ] O gatilho principal é o push remoto para `develop`.
- [ ] Havendo diferenças para `main`, um PR `develop → main` é criado se ainda não existir; existindo, o trabalho continua no mesmo PR (AC19).
- [ ] Push sem diferenças não cria PR (AC19).
- [ ] Push após um merge abre outro PR quando houver novas diferenças (AC19).
- [ ] `develop` permanece existente; a exclusão automática do branch fica desabilitada.
- [ ] O fluxo não depende exclusivamente de um evento de pull request produzido pelo token padrão do Actions, cujas regras de disparo e aprovação são próprias.
