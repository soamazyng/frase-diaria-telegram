# Proteção de main e merge manual

## Comportamento

`main` está protegida no GitHub real (não só documentada): push direto é
recusado, mesmo para a conta administradora, exigindo que as 5 verificações
da pipeline `CI/CD develop -> main` (ticket 18) estejam presentes e verdes.
O repositório aceita apenas merge commit (spec 4.11) — squash e rebase estão
desligados no nível do repositório, então nenhum merge futuro pode recriar
o problema de SHA já corrigido no ticket 20.

Um novo workflow, `.github/workflows/verificar-merge.yml`, roda depois de
qualquer PR mergeado em `main` e faz só duas coisas: confirma que a ponta de
`develop` incorporada é equivalente ao que está de fato implantado em
produção, e registra o resultado. Nunca publica (AC27).

## Decisão técnica

**Proteção de branch via API clássica (`branches/{branch}/protection`), não
Rulesets.** O ticket pede exatamente o que essa API cobre — checks
obrigatórios, `enforce_admins`, bloqueio de force-push/deleção — sem
necessidade dos recursos mais recentes (regras por padrão de branch,
bypass por ator). Nenhuma proteção prévia existia (`404 Branch not
protected`, conferido antes de aplicar), então não há migração a considerar.

**5 checks obrigatórios, pelo nome exato do job/check-run**, conferidos ao
vivo contra o HEAD de `develop` antes de escrever a policy (não presumidos):
`Garantir PR develop -> main`, `Testes, análise estática e validação SAM`,
`Construir artefato`, `Publicar em produção` (os 4 jobs do ticket 18) e
`GitGuardian Security Checks` (app externo já rodando em todo PR). `strict:
false` — a checagem de atualidade contra `main` já é feita pela própria
pipeline (ticket 18, com a correção do ticket 20), então exigir a flag padrão
do GitHub aqui seria uma segunda verificação da mesma coisa, com uma lógica
mais grosseira (compara contra o HEAD literal, não contra o segundo parent).

**`required_pull_request_reviews` deliberadamente `null` (não exigido).**
Projeto de usuária única (spec, fora de escopo — múltiplos usuários); exigir
aprovação forçaria um segundo papel só para clicar "aprovar" na própria
mudança, sem ganho de segurança real.

**Verificação pós-merge usa a API de Deployments, não credenciais AWS.** A
alternativa óbvia — perguntar à CloudFormation qual versão está ativa —
exigiria uma nova entrada na trust policy OIDC para o evento `pull_request`,
cujo formato de claim `sub` já surpreendeu duas vezes nesta sessão (tickets
18 e 19) e uma terceira vez de forma indireta no ticket 20. A API de
Deployments (ambiente `producao`) já é a fonte de verdade que os tickets
18–20 usam para "qual é a última publicação bem-sucedida" — reutilizá-la
aqui evita superfície OIDC nova inteiramente. Trade-off aceito: se alguém um
dia publicar por fora do pipeline (o procedimento manual de último recurso
documentado no ticket 19), essa verificação ficaria desatualizada até a
próxima publicação registrar um novo deployment — mesma limitação que o
ticket 19 já aceita para "localizar última publicação saudável".

**Ambiente de deployment próprio (`main-estavel`), não reaproveitar
`producao`.** Os tickets 19/20 já fazem buscas específicas em
`environment=producao` esperando encontrar tentativas de publicação; misturar
um registro de auditoria de merge nessa mesma lista arriscaria confundir
essas buscas.

## Verificação

- **Plano do GitHub confirmado ao vivo, não presumido:** `gh api user --jq
  .plan` → `pro`, imediatamente antes de aplicar a policy (o `CLAUDE.md` já
  registrava essa decisão, mas o checklist do ticket exige conferir antes de
  declarar concluído, não só herdar a decisão).
- **Proteção aplicada de verdade:** `PUT .../branches/main/protection`
  respondeu com a configuração completa (checks, `enforce_admins: true`,
  `allow_force_pushes: false`, `allow_deletions: false`).
- **AC29 exercitado contra o repositório real, não só inspecionado:** um
  push direto para `main` com um commit vazio descartável foi recusado pelo
  GitHub — `GH006: Protected branch update failed... 5 of 5 required status
  checks are expected`. A primeira tentativa usou uma referência local
  desatualizada de `origin/main` e falhou por motivo errado (não
  fast-forward, não proteção); repetida depois de `git fetch`, confirmou a
  rejeição correta.
- **`allow_squash_merge`/`allow_rebase_merge` confirmados `false`,
  `allow_merge_commit` `true`** via `gh api PATCH` no repositório.
- `.github/workflows/verificar-merge.yml` validado com `yaml.safe_load`,
  `actionlint` e `shellcheck` — zero achados.
- Revisão pela skill `github-actions-hardening`: nenhum achado — trigger
  `pull_request` (não `pull_request_target`), sem checkout, sem `uses:` de
  terceiros, permissões mínimas por job (`deployments: write`, `issues:
  write`, sem `contents`), nenhum `${{ }}` interpolado em `run:`.
- **Fluxo completo exercitado ao vivo, PR #6:** mergeada com merge commit
  (`<COMMIT_SHA>`), incorporando a ponta de `develop` `<COMMIT_SHA>`. O merge passou
  pela proteção normalmente (os 5 checks já estavam verdes) e disparou
  `verificar-merge.yml`. O passo "Localizar a última publicação
  bem-sucedida" achou `<COMMIT_SHA>` como implantação `success` mais recente —
  igual ao SHA incorporado — e "Marcar a versão como estável" criou o
  deployment `<DEPLOYMENT_ID>` no ambiente `main-estavel` com `state=success`.
  "Registrar divergência" ficou `skipped` (o caminho certo, já que os SHAs
  coincidiam) e nenhuma issue nova foi criada.

## Review

`security-review` de aplicação não se aplica — sem código Python nesta
entrega. `/code-review` (agente em background) sobre o diff completo do
ticket encontrou 3 achados:

- **Corrigido — corretude:** "Localizar a última publicação bem-sucedida"
  logava `::error::` quando nenhuma implantação `success` era encontrada,
  mas não interrompia o passo — a execução seguia com `sha=""`, e o passo
  seguinte abriria uma issue de "divergência" com SHA implantado vazio e
  texto sugerindo que uma recuperação automática trocou a versão ativa,
  quando na verdade nenhuma implantação foi encontrada. Corrigido com
  `exit 1`: sem `always()` nos passos seguintes, os dois ficam `skipped` e
  o job falha de forma visível, sem diagnóstico errado.
- **Aceito, não corrigido — duplicação/baixa:** o loop "achar a última
  implantação `success`" já existia, com pequenas variações
  (`per_page`, o que pula), em `pr-develop-main.yml` (ticket 19) e
  `reconciliador.yml` (ticket 20); esta é a terceira cópia. Mesmo
  trade-off já documentado nos dois tickets anteriores — extrair uma
  composite action arriscaria reintroduzir uma regressão sutil em lógica
  já exercitada ao vivo, sem tempo de testar de novo com o mesmo rigor.
- **Aceito, não corrigido — robustez/baixa:** "Registrar divergência" não
  tem verificação de idempotência antes de `gh issue create` — um re-run
  manual do workflow ou uma redelivery do webhook `pull_request` criaria
  uma issue duplicada. Confirmado que os dois `gh issue create`
  pré-existentes do projeto (tickets 19 e 20) têm exatamente a mesma
  lacuna, nunca corrigida — não é uma regressão introduzida aqui, e
  corrigir só esta cópia criaria tratamento inconsistente entre os três
  pontos. Risco baixo: no máximo ruído (issue duplicada), nunca corrupção
  de estado ou reenvio indevido.

## Próximo passo

Ticket 22 — documentação de operação e aceite real controlado — depende
deste ticket e do 15 (`/status` completo, ainda não implementado). Falta
`/status` antes de poder fechar o MVP.
