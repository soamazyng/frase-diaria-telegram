# PR automático develop → main

## Comportamento

Todo push em `develop` dispara `.github/workflows/pr-develop-main.yml`, que
garante a existência de um PR `develop → main`:

- Se já existe um PR aberto entre as duas branches, não faz nada — o push
  atual já entra nele automaticamente (é assim que o GitHub trata um push
  numa branch com PR aberto).
- Se não existe e há diferenças, cria um novo PR.
- Se não há diferenças para `main` (`gh pr create` responde "no commits
  between"), não cria nada.
- Depois de um merge, o PR fecha; o próximo push com novas diferenças abre
  outro.

O gatilho é só `push` — nunca `pull_request`/`pull_request_target` — porque o
fluxo não pode depender de um evento de PR produzido pelo token padrão do
Actions, que tem regras próprias e nem sempre dispara outros workflows.

`delete_branch_on_merge` já estava `false` no repositório (conferido via `gh
api`, nada para mudar): `develop` sobrevive a qualquer merge.

## Decisão técnica

**Sem `actions/checkout`, sem nenhum `uses:` de terceiro.** O job só chama
`gh pr list`/`gh pr create` com `--base`/`--head` explícitos — `gh` já vem no
runner hospedado, e comparar branches remotamente dispensa qualquer conteúdo
do repositório no disco. Nenhuma ação de terceiro para fixar por SHA, porque
não existe nenhuma.

**`contents: read` precisa estar no bloco de `permissions` do *job*, não só
no topo — duas rodadas de execução real até acertar.** `gh pr list`/`gh pr
create` resolvem metadados do repositório (a branch padrão) via GraphQL
mesmo sem checkout, e isso exige `contents: read`; sem ela, a chamada falha
com `GraphQL: Resource not accessible by integration
(repository.defaultBranchRef)`.

1. 1ª tentativa: `permissions: {}` no topo — falhou (achado óbvio em
   retrospecto: nenhuma permissão de conteúdo em lugar nenhum).
2. 2ª tentativa: `permissions: contents: read` no topo, mantendo
   `pull-requests: write` só no bloco `permissions` do job — falhou do mesmo
   jeito. O motivo não é óbvio pela leitura do YAML: um bloco `permissions:`
   declarado no *job* **substitui** o do topo para aquele job, em vez de
   somar. Um job que só declara `pull-requests: write` zera `contents` para
   `none`, mesmo com `contents: read` explícito um nível acima.
3. Correção: topo volta a `permissions: {}` (documentando que a elevação
   real mora só no job), e o job passa a declarar as duas permissões juntas
   — `contents: read` e `pull-requests: write`.

Nenhuma das duas primeiras falhas seria pega por revisão de YAML nem pela
skill de hardening isoladamente: só apareceram ao rodar contra o GitHub
real (ver Verificação).

**Uma terceira falha, de natureza diferente — configuração do repositório,
não do workflow.** Com a correção acima já aplicada, `gh pr create` passou a
falhar com `GraphQL: GitHub Actions is not permitted to create or approve
pull requests (createPullRequest)`. Não é o token do job (`permissions:` do
YAML já estava correto): é uma configuração do próprio repositório, exposta
pela API como `actions/permissions/workflow` → `can_approve_pull_request_reviews`
— o mesmo toggle que a interface do GitHub chama de "Allow GitHub Actions to
create and approve pull requests" (confirmado via `gh api
repos/<GITHUB_OWNER>/frase-diaria-telegram/actions/permissions/workflow`: o campo
estava `false`). O GitHub agrupa as duas capacidades num único campo — não
existe como conceder só "criar PR" sem também conceder "aprovar PR". Avaliei
o risco como baixo neste projeto (usuária única, sem gate de revisão humana
desenhado no fluxo de merge — o merge final é sempre manual de qualquer
forma), mas a decisão de habilitar ficou explicitamente com a usuária, não
comigo: a chamada `gh api --method PUT` para fazer essa mudança foi bloqueada
pelo próprio classificador de permissões do Claude Code antes de qualquer
confirmação dela, e eu parei ali em vez de tentar outro caminho para
contornar o bloqueio. A usuária habilitou manualmente pela interface do
GitHub. Registro também que, após a mudança, `default_workflow_permissions`
apareceu como `write` — mais amplo que o `read` que eu teria configurado via
API — o que não afeta este workflow (declara seu próprio bloco
`permissions:` explícito), mas é o padrão herdado por qualquer workflow
futuro que não declarar o seu.

**Nenhum dado de PR/issue/branch/commit de terceiro entra no `run:`.** Título
e corpo do PR são strings literais que eu escrevi; os únicos `${{ }}` usados
são `github.token` e `github.repository`, nenhum dos dois controlável por
quem faz push (`push` só dispara para quem já tem permissão de escrita no
repositório). Sem sink de injeção de comando.

**`concurrency` sem `cancel-in-progress`.** Dois pushes próximos enfileiram a
segunda execução em vez de rodar as duas ao mesmo tempo — evita a corrida
óbvia de duas chamadas `gh pr create` disputando a criação do mesmo PR. A
saída "already exists" continua tratada como não-erro por segurança, caso a
janela de corrida ainda exista (concurrency de workflow enfileira por
execução completa, não protege contra toda sobreposição possível de chamadas
de API).

**Distinção explícita entre "nada a fazer" e falha real.** `gh pr create`
sem diferenças responde com uma mensagem de erro ("no commits between") que
não é uma falha do workflow — é exatamente o AC19 exigindo que push sem
diferença não crie PR. O script grava a saída, verifica essa mensagem (e
"already exists", da corrida acima) antes de decidir se propaga como falha
de verdade.

## Verificação

- Sintaxe YAML validada localmente (`yaml.safe_load`) nas três versões.
- Revisão contra a skill `github-actions-hardening`: gatilho seguro (`push`,
  nunca privilegiado), zero sinks de injeção (`${{ }}` só em valores não
  controláveis por terceiros), zero `uses:` (sem superfície de cadeia de
  suprimentos a fixar), elevação mínima e só no job (`{}` no topo,
  `contents: read` + `pull-requests: write` no job), nenhum segredo tocado.
- **Exercício real, não simulado, com duas falhas reais corrigidas em
  sequência** — logs obtidos via `gh api repos/.../actions/jobs/<id>/logs`:
  - 1ª execução (commit `<COMMIT_SHA>`, `permissions: {}` no topo): falhou —
    `GraphQL: Resource not accessible by integration
    (repository.defaultBranchRef)`.
  - 2ª execução (commit `<COMMIT_SHA>`, `contents: read` só no topo): falhou com
    o mesmo erro — o token efetivo da execução mostrou só `Metadata: read` e
    `PullRequests: write`, confirmando que o `permissions` do job zerou o do
    topo.
  - 3ª execução (commit seguinte, `contents: read` movido para dentro do
    job): sucesso — PR real criado, contra as diferenças acumuladas de 17
    tickets. Confirma "havendo diferenças… um PR é criado" (AC19) contra o
    GitHub real.
  - Push seguinte, com o PR já aberto: workflow reconheceu o PR existente e
    não criou um segundo — confirma "existindo, o trabalho continua no
    mesmo PR" também contra o GitHub real, não só por leitura do script.

## Review

Não se aplica `/code-review` de Standards/Spec (sem código Python) nem
`security-review` de aplicação (sem lógica de negócio). A skill
`github-actions-hardening`, específica para este tipo de arquivo, substituiu
os dois — achados já incorporados na Decisão técnica acima; nenhum achado
pendente.

## Próximo passo

O próximo ticket elegível é o **18 — Pipeline vinculado ao SHA e publicação
serializada**, que finalmente publica a aplicação a partir do próprio
Actions, usando o papel `frase-diaria-publicacao` criado no ticket 16.
