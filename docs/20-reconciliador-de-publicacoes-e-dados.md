# Reconciliador de publicações e compatibilidade de dados

## Comportamento

Um novo workflow, `.github/workflows/reconciliador.yml`, roda de hora em
hora (decisão da usuária, mesma estimativa de custo do ticket 01) e também
por disparo manual (`workflow_dispatch`). Cobre os dois casos que a
recuperação síncrona do ticket 19 não cobre, porque ninguém está lá para
reagir:

1. **Runner interrompido no meio de uma publicação** — a implantação fica
   registrada `in_progress` para sempre na API de Deployments do GitHub,
   confundindo qualquer busca futura por "última publicação saudável"
   (ticket 19). O reconciliador marca como `error` qualquer implantação
   `in_progress` há mais de 20 minutos.
2. **PR fechado sem merge** (AC25, deixado pendente pelo ticket 19) — sem
   PR aberto `develop -> main`, se a versão publicada divergir do HEAD de
   `main`, é sinal de candidata abandonada (ou publicação nunca
   sincronizada). O reconciliador baixa o artefato de `main` (sem
   reconstruir), confere o checksum, republica e verifica — mesmo padrão
   do ticket 19. Sem sucesso, desabilita o agendamento diário e abre uma
   issue, mesmo padrão também.

Roda a partir de `main` com o papel `frase-diaria-infraestrutura`, agora
ampliado (`infra/bootstrap.yaml`) com as mesmas permissões de deploy do
papel de publicação — antes só lia o estado da stack, sem poder agir.

## Decisão técnica

**Papel de infraestrutura ampliado, decisão confirmada pela usuária.**
Criado só-leitura no ticket 16 ("a lógica de recuperação ainda não
existia"); agora precisa republicar de verdade. Escopado exatamente igual
ao papel de publicação — mesma stack `frase-diaria-app`, nunca a stack de
dados, nunca um recurso fora do prefixo do projeto.

**CloudFormation recusa âncora/alias YAML — achado ao vivo, não
presumido.** A primeira tentativa foi definir as 10 statements de deploy
uma única vez (âncoras `&nome`) e referenciá-las nos dois papéis via alias
(`*nome`) — o mesmo padrão que `infra/aplicacao.yaml` já usa. `aws
cloudformation validate-template` recusou com `"YAML aliases are not
allowed in CloudFormation templates"`. Funciona em `infra/aplicacao.yaml`
só porque o **SAM CLI resolve as âncoras do lado do cliente** antes de
enviar; `infra/bootstrap.yaml` vai direto via `aws cloudformation deploy`,
sem essa etapa. Revertido para duplicação explícita das 10 statements, com
um comentário de aviso no bloco de origem (`PapelDePublicacao`) apontando
para o bloco duplicado — mantê-los em sincronia manualmente é o trade-off
aceito, análogo à duplicação da lógica de download+deploy descrita abaixo.

**Incidente real ao aplicar: `UPDATE_ROLLBACK_FAILED`.** A primeira
tentativa de aplicar a nova policy também mudava o texto da `Description`
do papel. Isso disparou `iam:UpdateRoleDescription`, ação que a identidade
local (`user/aws-developer-group`) não tem — o `UPDATE` falhou, e o
**rollback automático também falhou pelo mesmo motivo**, travando a stack
em `UPDATE_ROLLBACK_FAILED`. Nenhuma mutação real chegou a ser aplicada
(conferido: `aws iam get-role` mostrou o papel intacto, no estado
anterior). Destravado com
`aws cloudformation continue-update-rollback --resources-to-skip PapelDeInfraestrutura`,
e a `Description` do papel mantida inalterada na segunda tentativa — que
aplicou só a mudança de policy (`iam:PutRolePolicy`, ação que já tinha
funcionado nas mutações anteriores desta sessão) e completou
`UPDATE_COMPLETE`.

**Lógica de download+deploy duplicada do ticket 19, não extraída para uma
composite action compartilhada.** O passo "Recuperar" do job `publicar`
(ticket 19) já está exercitado ao vivo várias vezes contra produção real
nesta sessão. Refatorá-lo para extrair uma composite action reutilizável
aqui arriscaria reintroduzir uma regressão sutil (como o `always()`
faltando, achado só ao vivo) sem tempo de reexercitar com o mesmo rigor.
Trade-off deliberado, não descuido — a mesma decisão já tomada para as
policies IAM duplicadas acima.

**Detecção de "PR fechado sem merge" por comparação, não por evento.**
Sem escutar o evento `pull_request: closed` diretamente (que exigiria
ampliar a trust policy OIDC para o formato `pull_request` do claim `sub`,
decisão adiada explicitamente no ticket 19), o reconciliador infere o
mesmo resultado por inferência: sem PR aberto `develop -> main`, a versão
publicada *deveria* ser exatamente o HEAD de `main`; qualquer divergência
é candidata abandonada. Com PR aberto, a stack rodar o conteúdo da
candidata é esperado (spec, 4.11) — o reconciliador não interfere num
`publicar` em andamento pelo próprio pipeline. Idempotente por
construção: se a versão ativa já é a estável, não faz nada.

## Verificação

- `.github/workflows/reconciliador.yml` validado com `yaml.safe_load`,
  `actionlint` e `shellcheck` — zero achados (um falso positivo do
  `shellcheck` sobre acentos graves numa query JMESPath foi resolvido
  trocando `--query` por `--output json` + `jq`, mais consistente com o
  resto do projeto de qualquer forma).
- Revisão pela skill `github-actions-hardening`: nenhum achado —
  `permissions` mínimas e escopadas às ações realmente usadas, nenhum
  `${{ }}` direto em `run:`, actions de terceiro reaproveitadas das já
  auditadas nos tickets 18/19, triggers (`schedule`/`workflow_dispatch`)
  não privilegiados.
- `infra/bootstrap.yaml`: as 10 statements da policy nova conferidas
  programaticamente como idênticas às do papel de publicação (script
  Python com loader YAML compatível com tags do CloudFormation),
  aplicadas na AWS real (`UPDATE_COMPLETE`, após o incidente de rollback
  acima) e a policy `PublicarStackDeAplicacao` do papel de infraestrutura
  conferida ao vivo (`aws iam get-role-policy`) com os 10 `Sid` esperados.
- **Exercitado ao vivo após o merge do PR #2, sessão de 2026-09-08.**
  `gh workflow run reconciliador.yml --ref main` disparado logo depois do
  merge para `main`. Claim `sub` do OIDC confirmado contra o token real:
  `repo:soamazyng@443219/frase-diaria-telegram@1359588301:ref:refs/heads/main`
  — exatamente o formato já assumido na trust policy do papel de
  infraestrutura (`infra/bootstrap.yaml`). `AssumeRoleWithWebIdentity`
  funcionou de primeira; passo de debug removido neste commit. A ampliação
  de IAM do papel de infraestrutura foi usada de verdade pela primeira vez
  (`sam deploy` real na tentativa de reconciliação abaixo).
- **Achado real: "versão estável" presume merge fast-forward, e
  `gh pr merge --merge` não é fast-forward.** O passo "Avaliar" comparou o
  HEAD de `main` (commit de merge `100e337`, criado pelo merge do PR #2)
  contra a versão publicada (`8fc30fa`, o commit de `develop` testado pelo
  pipeline) e viu divergência real — mas um commit de merge tradicional
  sempre gera um SHA novo que nunca passou pelo CI/CD, então nenhum
  artefato existia para `100e337` (`gh api .../actions/artifacts?name=...`
  vazio). A reconciliação seguiu o caminho de falha por desenho: **abriu a
  issue #4** e **desabilitou de verdade o agendamento diário**
  (`frase-diaria-agendador-diario` → `DISABLED`). Não é uma falha de
  publicação — a versão em produção (`8fc30fa`) sempre esteve correta e
  saudável. Reativado manualmente (`aws scheduler update-schedule` →
  `ENABLED`, confirmado) e a issue #4 comentada explicando o falso positivo
  e fechada, minutos depois do incidente. **Causa raiz não corrigida nesta
  sessão** (decisão explícita: registrar o achado e decidir a correção
  depois) — ver "Próximo passo".
- Caminho "implantação travada" também exercitado nesta mesma execução,
  sem incidente: nenhuma implantação `in_progress` havia mais de 20
  minutos, então o passo não teve o que reconciliar.
- **Mesmo achado, segundo efeito real: o guard de publicação do próprio
  ticket 18 também quebrou.** O push seguinte para `develop` (commit
  `58d2efd`, este ticket) foi bloqueado pelo passo "Reconsultar PR aberto,
  SHA atual e base de main" — `gh api compare/main...develop` acusou
  `diverged`, não `ahead`, porque `develop` nunca incorporou de volta o
  commit de merge `100e337`. Abortou com segurança **antes** de tocar o
  deploy (produção seguiu em `8fc30fa`, saudável) — o guard funcionou
  exatamente como desenhado, só que a suposição por trás dele (histórico
  linear entre `develop` e `main`) já não era mais verdadeira depois de um
  merge commit. Corrigido mesclando `main` de volta em `develop`
  (`dffa16f`, sem mudança de conteúdo) — publicação seguinte confirmada
  verde, versão ativa = `dffa16f` (exatamente o SHA testado). Padrão usual
  de git-flow após merge de release, mas **precisa virar prática
  obrigatória documentada**, não uma correção pontual — ver "Próximo
  passo".

## Review

Não se aplica `/code-review` de Standards/Spec em dois eixos nem
`security-review` de aplicação — sem código Python nesta entrega, só
infraestrutura (`infra/bootstrap.yaml`) e workflow YAML.

## Próximo passo

1. **Decidir a política de merge `develop -> main`, agora com dois pontos
   de quebra confirmados ao vivo** (o guard de publicação do ticket 18 e o
   caminho de reconciliação deste ticket) — não só o reconciliador.
   Direções possíveis, nenhuma decidida: (a) exigir merge fast-forward de
   `develop -> main` (sem commit de merge novo, elimina o problema na
   raiz); (b) manter merge commit, mas tornar obrigatório mesclar `main`
   de volta em `develop` logo em seguida (o que resolveu ao vivo desta
   vez, mas depende de lembrar de fazer manualmente); (c) comparar contra
   o primeiro parent do commit de merge em vez do HEAD literal, nos dois
   lugares que presumem SHA vinculado.
2. **Ticket 21** — proteção de `main` e merge manual — já não está mais
   bloqueado por dependências (18 e 20 concluídos), mas herda o mesmo
   achado: qualquer proteção de `main` que dependa de "HEAD de main = SHA
   vinculado" precisa da mesma decisão do item 1 antes de ser implementada
   em cima disso.
