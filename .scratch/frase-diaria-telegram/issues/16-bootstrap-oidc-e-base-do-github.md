# 16 — Bootstrap OIDC AWS e base do GitHub

**What to build:** o GitHub Actions passa a conseguir assumir papel na AWS com credenciais temporárias, sem nenhuma chave permanente guardada no repositório. Como um pipeline sem confiança não consegue criar a própria autorização, este passo é executado uma única vez por uma identidade AWS já autorizada.

**Blocked by:** 01 — Elegibilidade e estimativa de custo AWS/GitHub.

**Status:** concluído em 2026-09-08 — ver `docs/16-bootstrap-oidc-e-base-do-github.md`

- [x] Configuração de bootstrap declarativa, com instrução de execução única a partir de uma identidade AWS já autorizada.
- [x] Confiança OIDC restrita a proprietário e repositório, com audience e subject validados e contexto de execução autorizado (AC28).
- [x] Papel de publicação e papel de execução da infraestrutura separados, cada um com escopo controlado.
- [x] A permissão de emissão de token de identidade é concedida somente ao trabalho que precisa assumir papel AWS.
- [x] Repositório privado com `develop` e `main` permanentes; `develop` criada a partir de `main`.
- [x] `main` inicializada com o necessário para os workflows e a configuração do repositório, sem precisar publicar uma versão do bot.
- [x] Políticas efetivas do GitHub e a permissão para Actions criarem PR verificadas e registradas.
- [x] Nenhum segredo aparece no Git nem nos logs (AC28).
