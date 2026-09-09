# 21 — Proteção de main e merge manual

**What to build:** `main` passa a só aceitar código que já foi publicado e verificado em produção, e a decisão final continua sendo da desenvolvedora. O merge de uma candidata saudável apenas a registra como estável — não dispara uma segunda publicação.

**Blocked by:** 18 — Pipeline vinculado ao SHA e publicação serializada; 20 — Reconciliador de publicações e compatibilidade de dados.

**Status:** concluído em 2026-09-09 — ver
`docs/21-protecao-de-main-e-merge-manual.md`.

- [x] `main` protegida contra push direto, exigindo o conjunto de checks obrigatórios, incluindo a publicação validada. *(branch protection real via API, 5 checks obrigatórios exatos do ticket 18 + GitGuardian)*
- [x] Caminhos de bypass desabilitados quando aplicável. *(`enforce_admins: true`, `allow_force_pushes`/`allow_deletions: false`; bypass por ator não existe no plano Pro, não aplicável)*
- [x] A exigência é exercitada no repositório real e impede merge com checks falhos ou ausentes (AC29). *(push direto real recusado: `GH006: Protected branch update failed... 5 of 5 required status checks are expected`)*
- [x] Compatibilidade do plano do GitHub com exigência automática em repositório privado verificada; se não houver suporte, a incompatibilidade é apresentada sem tornar o repositório público nem relaxar a exigência. *(`gh api user` confirmou plano `pro` ao vivo antes de aplicar; aplicação bem-sucedida confirma suporte)*
- [x] O merge é manual, em merge commit que preserva o histórico de `develop`, e `develop` continua existindo. *(`allow_squash_merge`/`allow_rebase_merge` desligados no repositório; `develop` nunca foi tocado)*
- [x] A verificação de merge corresponde ao código atualmente implantado; uma recuperação invalida esse resultado mesmo que o SHA já tenha passado antes. *(compara contra a última implantação `success` da API de Deployments, não contra o SHA testado no momento do PR)*
- [x] Após o merge, registra-se qual SHA testado foi incorporado, valida-se a equivalência de conteúdo e a versão é marcada como estável. *(`.github/workflows/verificar-merge.yml`, exercitado ao vivo na PR #6 — deployment `main-estavel` registrado)*
- [x] O evento de merge não refaz a publicação (AC27). *(workflow só lê a API de Deployments e registra outra; nunca chama `sam deploy`/`make publicar-app`)*
