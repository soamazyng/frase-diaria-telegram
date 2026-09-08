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
- **Não exercitado ao vivo — limitação estrutural, não pendência
  minha:** GitHub só ativa `schedule`/`workflow_dispatch` para um workflow
  a partir do conteúdo da **branch padrão** (`main`). Como este arquivo só
  existe em `develop` até agora, `gh workflow list` nem sequer lista o
  reconciliador, e `gh workflow run` falha com "could not find any
  workflows". Isso vale tanto para o disparo manual de teste quanto para o
  cron de hora em hora — nenhum dos dois vai rodar antes do merge do PR
  `develop -> main` (#2). Um passo de debug temporário (mesmo padrão do
  ticket 18) foi incluído no workflow para confirmar o claim `sub` do OIDC
  na primeira execução real — ainda não removido, porque ainda não pôde
  rodar. Isso também significa que a ampliação de IAM do papel de
  infraestrutura, embora aplicada e conferida na AWS, ainda não foi
  **usada** de verdade por nenhum workflow.

## Review

Não se aplica `/code-review` de Standards/Spec em dois eixos nem
`security-review` de aplicação — sem código Python nesta entrega, só
infraestrutura (`infra/bootstrap.yaml`) e workflow YAML.

## Próximo passo

1. **Merge do PR `develop -> main` (#2)** — decisão da usuária. Só depois
   disso o reconciliador passa a existir de verdade para o GitHub, e o
   claim `sub` do OIDC para `schedule`/`workflow_dispatch` pode ser
   confirmado contra um token real (ou corrigido, se a suposição
   `ref:refs/heads/main` estiver errada, como já aconteceu duas vezes
   nesta sessão com outros triggers).
2. Depois de confirmado o claim `sub`: remover o passo de debug, e
   idealmente provocar um teste real de cada caso (implantação travada,
   PR fechado sem merge) — mesmo espírito dos testes de fogo do ticket 19.
3. **Ticket 21** — proteção de `main` e merge manual — já não está mais
   bloqueado só por este ticket; falta decidir também quando fazer esse
   primeiro merge real.
