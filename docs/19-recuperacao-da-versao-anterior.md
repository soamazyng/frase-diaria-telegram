# Recuperação da versão anterior

## Escopo desta entrega

A spec (4.12) e o checklist do ticket cobrem três gatilhos de recuperação:
**falha de deploy**, **falha de diagnóstico pós-publicação** e **fechamento
de PR sem merge**. Esta entrega cobre os dois primeiros — os únicos
síncronos, presos ao mesmo job `publicar` e à mesma exclusão mútua já
existentes desde o ticket 18. O terceiro (AC25) fica para uma próxima
sessão: recuperá-lo exige que um workflow disparado por `pull_request`
assuma o papel de publicação, e o claim `sub` do OIDC para esse tipo de
evento é `repo:DONO@ID/REPO@ID:pull_request` — sem branch, diferente do
`ref:refs/heads/develop` que a trust policy exige hoje (verificado contra a
documentação oficial do GitHub, não presumido). Ampliar essa confiança é
uma decisão de segurança que merece ser tratada isolada, não emendada
numa entrega já grande. Ver "Próximo passo".

Decisão confirmada pela usuária: o "desabilitar novos envios" da spec é
resolvido só por infraestrutura (desligar o `ScheduleV2` da diária via
`scheduler:UpdateSchedule`, já concedido ao papel de publicação desde o
ticket 16) — sem flag de aplicação nova em `aplicacao/`, o que exigiria
código Python e testes numa entrega que já estava grande.

## Comportamento

O passo "Verificar saúde, versão, dependências, webhook e agendamento" do
job `publicar` (ticket 18) foi extraído para uma *composite action*
reutilizável, `.github/actions/diagnosticar-publicacao`, parametrizada pela
versão esperada. O job passa a rodá-la **sempre** (`if: always()`), mesmo
que `sam deploy` tenha falhado — porque o CloudFormation pode ter feito
rollback nativo sozinho, e só o diagnóstico revela se esse rollback deixou
algo saudável.

Quando o diagnóstico reprova (deploy falho sem rollback suficiente, ou
deploy bem-sucedido mas sistema doente):

1. **Localizar última publicação saudável** — percorre a API de
   Deployments do GitHub (já existente desde o ticket 18), do mais recente
   para o mais antigo, pulando a implantação desta própria tentativa, até
   achar a última com `state=success`. Essa API já É o marco "publicação
   saudável anterior à tentativa" (checklist do ticket 19) — nenhum
   manifesto novo foi criado.
2. **Recuperar** — baixa o artefato **já construído** daquele SHA (de uma
   execução passada deste mesmo workflow, via `actions/artifacts` API),
   confere o checksum, e publica com `make publicar-app-artefato
   VERSAO=<sha antigo>` — sem reconstruir dependências (spec, 4.12). Registra
   uma implantação própria para essa recuperação.
3. **Verificar publicação recuperada** — a mesma composite action, agora
   contra o SHA recuperado.
4. Se **nada** disso resolve (sem publicação `success` anterior — "primeiro
   deploy sem versão anterior" — ou a própria recuperação falha): desliga o
   agendamento diário e abre uma issue no GitHub com o procedimento manual.

O marco "versão estável aceita em `main`" não precisou de nenhum mecanismo
novo: é literalmente o HEAD de `main`, consultável a qualquer momento via
`gh api repos/.../git/ref/heads/main` — só passa a ser usado quando a
recuperação do PR fechado (AC25) for implementada.

## Decisão técnica

**Reaproveitar a API de Deployments como os dois marcos exigidos, em vez de
um manifesto próprio.** A checklist pede "dois marcos... consultáveis":
publicação saudável anterior e versão estável em `main`. Os dois já existem
sem esforço adicional — implantações `success` (ticket 18) e o HEAD de
`main` (git, sempre a fonte de verdade) — desenhar um manifesto paralelo
duplicaria conhecimento (G5) sobre o mesmo fato.

**Artefato com retenção de 14 dias, não 1.** O ticket 18 deixou 1 dia de
propósito (o artefato só precisava sobreviver até o job seguinte do mesmo
run). A recuperação agora depende de baixar um artefato de uma execução
*passada* — sem ele, "sem reconstruir dependências" vira impossível depois
de 24h. 14 dias casa com a retenção de logs já padronizada no projeto
(`RetencaoDeLogsEmDias`, `infra/aplicacao.yaml`), sem inventar outro prazo.

**Composite action, não duplicar o script duas vezes.** O diagnóstico
precisa rodar duas vezes por tentativa (contra o SHA que falhou, contra o
SHA recuperado) com a mesma lógica exata — só a versão esperada muda. Uma
`.github/actions/diagnosticar-publicacao` local (mesmo repositório, mesmo
commit do workflow — sem risco de cadeia de suprimentos, sem precisar de
pin por SHA) evita ~80 linhas de bash duplicadas (G5).

**`aws scheduler update-schedule` não foi exercitado ao vivo contra o
agendamento real.** Testar de verdade significaria desligar por alguns
segundos o disparo real da diária de produção — um efeito colateral
observável para a usuária, não uma leitura inofensiva. A forma exata do
JSON foi conferida contra a AWS real, só em modo leitura: `aws scheduler
get-schedule` retorna exatamente as chaves que `update-schedule
--generate-cli-skeleton` espera (`ActionAfterCompletion`, `Description`,
`FlexibleTimeWindow`, `GroupName`, `Name`, `ScheduleExpression`,
`ScheduleExpressionTimezone`, `State`, `Target` — com `Target.Arn` e
`Target.RoleArn` aninhados, não confundir com o `Arn` do próprio
agendamento no nível raiz, que é removido antes do `update-schedule` por
ser campo somente-leitura). O `jq 'del(.CreationDate, .LastModificationDate, .Arn) | .State = "DISABLED"'`
foi desenhado a partir dessa forma real, não de suposição — mas o caminho
completo (do `get` até o `update` de fato aplicado) só será comprovado na
primeira vez que o gatilho disparar de verdade.

**Nenhuma mudança em `infra/bootstrap.yaml` nem em nenhuma policy IAM.** Os
dois casos cobertos aqui reusam exatamente o papel `frase-diaria-publicacao`
e as permissões que ele já tinha (`scheduler:UpdateSchedule`,
`scheduler:GetSchedule`, `cloudformation:*` na stack de aplicação) — nenhum
gap novo foi encontrado ao desenhar esta parte.

## Verificação

- `.github/workflows/pr-develop-main.yml` e a composite action nova
  validados com `yaml.safe_load`, `actionlint` e `shellcheck` (mesmas
  ferramentas isoladas em scratchpad dos tickets 17/18) — zero achados.
  `actionlint` não interpreta `action.yml` de composite actions (formato
  diferente de workflow); o script embutido foi extraído e passado pelo
  `shellcheck` isoladamente.
- Revisão pela skill `github-actions-hardening`: nenhum achado — todo
  `${{ }}` novo passa por `env:`, as duas permissões novas (`actions: read`,
  `issues: write`) são as mínimas exigidas pelos passos que as usam, e o
  download de artefato entre execuções nunca depende de dado controlável
  por terceiro (o nome do artefato vem de um SHA que o próprio pipeline
  registrou antes, nunca de entrada externa).
- Consultada a skill local `python-clean-code`: sem código Python nesta
  entrega; dos princípios gerais, aplicados **G5** (composite action em vez
  de duplicar o diagnóstico) e **C1-C4** (comentários justificam decisões —
  por que a API de Deployments substitui um manifesto, por que o AC25 fica
  de fora).
- **Não exercitado ao vivo nesta sessão:** nenhum dos dois caminhos de
  recuperação (falha de deploy, falha de diagnóstico) foi realmente
  disparado contra a AWS/GitHub reais — exigiria provocar uma falha de
  propósito num push real, um efeito observável em produção que não foi
  pedido nesta tarefa. A lógica foi revisada e validada estruturalmente,
  seguindo o mesmo padrão que funcionou nos tickets 16-18, mas — como o
  próprio `rules.md` do projeto lembra — "um guarda que nunca falhou não
  guarda nada". Recomendo um teste real controlado (quebrar o diagnóstico de
  propósito num push, observar a recuperação agir, restaurar) antes de
  considerar o AC24 comprovado, não só implementado.

## Review

Não se aplica `/code-review` de Standards/Spec em dois eixos nem
`security-review` de aplicação — sem código Python nesta entrega, só
workflow YAML e uma composite action.

## Próximo passo

Em aberto, nesta ordem de dependência:

1. **Exercitar de verdade** os dois caminhos implementados (falha de deploy
   com rollback nativo insuficiente; falha de diagnóstico com recuperação
   bem-sucedida) — decisão da usuária sobre quando provocar isso contra a
   produção real.
2. **AC25 — recuperação em PR fechado sem merge.** Precisa de uma decisão
   de segurança específica: ampliar a trust policy do papel de publicação
   para aceitar também o `sub` de eventos `pull_request` (perdendo a
   precisão de branch que o `ref:refs/heads/develop` atual garante), ou
   desenhar um caminho que não exija OIDC direto nesse trigger — por
   exemplo, deixar esse caso para o **ticket 20** (Reconciliador), que já
   está no seu escopo declarado ("cobrindo... falha do evento de fechamento
   do PR") e roda a partir de `main` com um papel (`frase-diaria-infraestrutura`)
   cuja trust policy já é compatível com esse branch.
3. Depois disso, ticket 20 segue bloqueado por este (19) como já estava.
