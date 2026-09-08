# 21 — Proteção de main e merge manual

**What to build:** `main` passa a só aceitar código que já foi publicado e verificado em produção, e a decisão final continua sendo da desenvolvedora. O merge de uma candidata saudável apenas a registra como estável — não dispara uma segunda publicação.

**Blocked by:** 18 — Pipeline vinculado ao SHA e publicação serializada; 20 — Reconciliador de publicações e compatibilidade de dados.

**Status:** ready-for-agent

- [ ] `main` protegida contra push direto, exigindo o conjunto de checks obrigatórios, incluindo a publicação validada.
- [ ] Caminhos de bypass desabilitados quando aplicável.
- [ ] A exigência é exercitada no repositório real e impede merge com checks falhos ou ausentes (AC29).
- [ ] Compatibilidade do plano do GitHub com exigência automática em repositório privado verificada; se não houver suporte, a incompatibilidade é apresentada sem tornar o repositório público nem relaxar a exigência.
- [ ] O merge é manual, em merge commit que preserva o histórico de `develop`, e `develop` continua existindo.
- [ ] A verificação de merge corresponde ao código atualmente implantado; uma recuperação invalida esse resultado mesmo que o SHA já tenha passado antes.
- [ ] Após o merge, registra-se qual SHA testado foi incorporado, valida-se a equivalência de conteúdo e a versão é marcada como estável.
- [ ] O evento de merge não refaz a publicação (AC27).
