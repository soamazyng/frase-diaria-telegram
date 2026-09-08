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

`permissions: contents: read` no topo, não `{}`. A primeira versão tentou
`{}` (nenhum passo lê arquivo algum, então parecia certo) e foi publicada —
essa primeira execução real falhou com `GraphQL: Resource not accessible by
integration (repository.defaultBranchRef)`: mesmo sem checkout, `gh pr
list`/`gh pr create` resolvem metadados do repositório via GraphQL, e isso
exige `contents: read`. Achado só ao exercitar contra o GitHub de verdade,
não por leitura do YAML; corrigido num segundo commit, sem reescrever o
primeiro (ver Verificação).

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

- Sintaxe YAML validada localmente (`yaml.safe_load`) nas duas versões.
- Revisão contra a skill `github-actions-hardening`: gatilho seguro (`push`,
  nunca privilegiado), zero sinks de injeção (`${{ }}` só em valores não
  controláveis por terceiros), zero `uses:` (sem superfície de cadeia de
  suprimentos a fixar), elevação mínima (`contents: read` no topo,
  `pull-requests: write` só no job), nenhum segredo tocado.
- **Exercício real, não simulado, incluindo uma falha real corrigida:**
  - 1ª execução (`permissions: {}`, commit `3b7fb17`): falhou —
    `GraphQL: Resource not accessible by integration
    (repository.defaultBranchRef)`, log obtido via
    `gh api repos/.../actions/jobs/<id>/logs`.
  - Corrigido para `contents: read` neste commit; resultado da execução
    seguinte (criação do PR contra as diferenças reais acumuladas de 17
    tickets, e o comportamento de push seguinte com o PR já aberto)
    confirmado logo abaixo, com o número real do PR.

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
