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
- **Caminho feliz exercitado de verdade, ao vivo:** o primeiro push real
  com estas mudanças (`gh run` `34285100609`) publicou de ponta a ponta —
  `sam deploy` real, diagnóstico aprovado pela composite action nova, e os
  seis passos novos de recuperação (`Localizar última publicação
  saudável`, `Recuperar`, `Verificar publicação recuperada`, `Registrar
  resultado da recuperação`, `Desabilitar agendamento`, `Registrar
  diagnóstico no GitHub`) todos `skipped`, exatamente o esperado quando o
  diagnóstico original passa. Isso comprova, contra o sistema real: a
  extração da composite action não quebrou o diagnóstico original, as
  novas `permissions:` (`actions: read`, `issues: write`) não impediram o
  job de completar, e as condições `if:` dos passos de recuperação
  corretamente não disparam fora do gatilho esperado.
- **Achado real no meio do caminho, não um bug do ticket 19:** a primeira
  tentativa desse mesmo push falhou na checagem "develop precisa incluir a
  base de main" (do ticket 18, inalterada aqui) com `status: diverged`. O
  PR #1 (develop → main) tinha sido mesclado por commit de merge enquanto
  o ticket 19 estava em desenvolvimento, e `develop` local nunca
  sincronizou de volta esse commit — um cenário genuinamente novo, nunca
  visto nas publicações do ticket 18. A checagem bloqueou corretamente
  (nenhuma mutação na stack aconteceu) e todos os passos de recuperação do
  ticket 19 ficaram inertes, como desenhado — a falha não era "diagnóstico
  reprovou", era "não deveria nem tentar publicar". Corrigido com
  `git merge origin/main` em `develop` (confirmado sem diferença de
  conteúdo: `git diff <merge-commit> <develop-anterior> --stat` vazio, só
  reconvergência de histórico) e reenviado — a segunda tentativa é o
  sucesso relatado acima. Isso valida essa checagem do ticket 18 contra um
  cenário real de merge pela primeira vez, e expõe uma lacuna operacional:
  nada no pipeline sincroniza `develop` de volta automaticamente depois de
  um merge — fica para o ticket 21 (proteção de `main`) considerar se isso
  merece automação.
- **Ainda não exercitado ao vivo:** os dois caminhos de recuperação em si
  (falha de deploy, falha de diagnóstico) — o push real desta sessão
  seguiu o caminho feliz. Provar que a recuperação de fato republica e
  verifica exigiria uma falha provocada de propósito, um efeito observável
  em produção que segue não pedido nesta tarefa. Recomendo esse teste
  controlado antes de considerar o AC24 comprovado, não só implementado e
  estruturalmente exercitado.

## Teste de fogo real — achado, corrigido, e o que ficou provado

A usuária pediu explicitamente o teste real de recuperação. Em vez de
quebrar o código da aplicação (o que a suíte de testes de `verificar`
pegaria antes mesmo de chegar em `publicar`), o teste mudou só o parâmetro
`Versao` do `sam deploy` para um valor propositalmente errado
(`quebrado-de-proposito-ticket-19`) — o artefato e o código real publicados
continuavam sendo exatamente os já aprovados em `verificar`; só o rótulo
cosmético que `/health` e o Output `VersaoPublicada` relatam ficou errado.
Deploy real, sem risco à funcionalidade do bot.

**O que aconteceu:** o diagnóstico reprovou como esperado (mismatch de
versão). "Localizar última publicação saudável" rodou e achou o SHA certo
(`e26cca1...`). Mas **"Recuperar publicação saudável anterior" nunca
rodou** — ficou `skipped` mesmo com o SHA já localizado — e a cadeia caiu
direto em "Desabilitar agendamento diário", que **desabilitou de verdade**
o `ScheduleV2` da diária em produção, e "Registrar diagnóstico no GitHub",
que abriu a issue #3 de verdade.

**Causa raiz:** os passos `Recuperar publicação saudável anterior` e
`Verificar publicação recuperada` tinham `if:` sem `always()`/`failure()`/
`cancelled()` explícito. O GitHub Actions insere um `success()` implícito
nesse caso — e como o passo `diagnostico` já tinha falhado (é exatamente
por isso que a recuperação deveria rodar), esse `success()` implícito
bloqueava os dois passos, apesar da condição explícita (`sha != ''`) ser
verdadeira. Nenhuma ferramenta estrutural (`actionlint`, `shellcheck`,
`yaml.safe_load`, a skill `github-actions-hardening`) pega esse tipo de
erro — é uma regra de semântica do runner, não de sintaxe.

**Resposta imediata:** o agendamento foi reabilitado manualmente
(`aws scheduler update-schedule`, conferido `ENABLED` antes de qualquer
outra coisa), os dois `if:` corrigidos com `always()`, o `Versao` de teste
revertido, tudo em um único commit (`904d85c`) — publicado e confirmado:
`/health` voltou a relatar o SHA real, agendamento `ENABLED`. A issue #3
foi fechada com o relato do que aconteceu.

**O que ficou provado, contra o sistema real:**
- O diagnóstico detecta corretamente um mismatch de versão.
- "Localizar última publicação saudável" acha o SHA certo na API de
  Deployments.
- "Desabilitar agendamento diário" funciona de ponta a ponta — o `jq` que
  reconstrói o payload de `update-schedule` a partir do `get-schedule` real
  estava certo (só não deveria ter sido alcançado neste caso).
- "Registrar diagnóstico no GitHub" cria a issue com o texto certo.

**O que ainda não ficou provado:** o próprio passo `Recuperar publicação
saudável anterior` — baixar o artefato de uma execução passada, conferir o
checksum, rodar `sam deploy` com o SHA antigo — nunca chegou a executar.
É o único trecho genuinamente novo e não testado do ticket 19; o próximo
teste de fogo (com o bug já corrigido) deve mirar exatamente nele.

## Review

Não se aplica `/code-review` de Standards/Spec em dois eixos nem
`security-review` de aplicação — sem código Python nesta entrega, só
workflow YAML e uma composite action.

## Próximo passo

Em aberto, nesta ordem de dependência:

1. **Repetir o teste de fogo** com o bug do `always()` já corrigido, para
   provar de verdade o passo `Recuperar publicação saudável anterior` (o
   único que ainda não rodou) — decisão da usuária sobre quando.
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
