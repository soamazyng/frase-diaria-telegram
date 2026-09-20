# Issue tracker: GitHub

Issues e specs de trabalho novo/planejamento (wayfinder, to-tickets, triage, to-spec) vivem
como issues do GitHub deste repositório. Use a CLI `gh` para todas as operações.

Os 29 tickets já concluídos antes desta configuração continuam em
`.scratch/frase-diaria-telegram/issues/*.md`, como registro histórico — não foram
migrados retroativamente para o GitHub (decisão explícita da usuária). Esta configuração
vale só para trabalho novo, a partir de agora.

## Convenções

- **Criar uma issue**: `gh issue create --title "..." --body "..."`. Use heredoc para corpos com várias linhas.
- **Ler uma issue**: `gh issue view <numero> --comments`, filtrando comentários com `jq` e buscando labels também.
- **Listar issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` com `--label` e `--state` apropriados.
- **Comentar numa issue**: `gh issue comment <numero> --body "..."`
- **Aplicar/remover labels**: `gh issue edit <numero> --add-label "..."` / `--remove-label "..."`
- **Fechar**: `gh issue close <numero> --comment "..."`

O repositório é inferido de `git remote -v`; `gh` já faz isso automaticamente dentro do clone.

## Pull requests como superfície de triagem

**PRs como superfície de pedido: não.** _(Mude para "sim" se este repo tratar PRs
externos como pedidos de funcionalidade; `/triage` lê essa flag.)_

## Quando uma skill disser "publique no rastreador de issues"

Criar uma issue no GitHub.

## Quando uma skill disser "busque o ticket relevante"

Rodar `gh issue view <numero> --comments`.

## Operações do wayfinder

Usado por `/wayfinder`. O **mapa** é uma única issue com issues **filhas** como tickets.

- **Mapa**: uma única issue rotulada `wayfinder:map`, guardando o corpo de Notes / Decisions-so-far / Fog. `gh issue create --label wayfinder:map`.
- **Ticket filho**: uma issue ligada ao mapa como sub-issue do GitHub (`gh api` no endpoint de sub-issues). Onde sub-issues não estiverem habilitadas, adicionar o filho a uma task list no corpo do mapa e colocar `Part of #<mapa>` no topo do corpo do filho. Labels: `wayfinder:<tipo>` (`research`/`prototype`/`grilling`/`task`). Uma vez reivindicado, o ticket é atribuído a quem está conduzindo.
- **Bloqueio**: as **dependências nativas de issue** do GitHub, a representação canônica e visível na UI. Adicionar uma aresta com `gh api --method POST repos/<owner>/<repo>/issues/<filho>/dependencies/blocked_by -F issue_id=<id-do-bloqueador>`, onde `<id-do-bloqueador>` é o **id de banco de dados** numérico do bloqueador (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, não o `#numero` nem o `node_id`). O GitHub relata `issue_dependencies_summary.blocked_by` (só bloqueadores abertos, o portão vivo). Onde dependências não estiverem disponíveis, usar como alternativa uma linha `Blocked by: #<n>, #<n>` no topo do corpo do filho. Um ticket é desbloqueado quando todo bloqueador estiver fechado.
- **Consulta de fronteira**: listar os filhos abertos do mapa (`gh issue list --state open`, restrito às sub-issues/task list do mapa), descartar os que tiverem um bloqueador aberto (`issue_dependencies_summary.blocked_by > 0`, ou uma issue aberta na linha `Blocked by`) ou um responsável atribuído; o primeiro na ordem do mapa vence.
- **Reivindicar**: `gh issue edit <n> --add-assignee @me`, a primeira escrita da sessão.
- **Resolver**: `gh issue comment <n> --body "<resposta>"`, depois `gh issue close <n>`, depois anexar um ponteiro de contexto (gist + link) ao Decisions-so-far do mapa.
