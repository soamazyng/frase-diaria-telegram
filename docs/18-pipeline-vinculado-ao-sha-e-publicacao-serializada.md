# Pipeline vinculado ao SHA e publicação serializada

## Comportamento

Todo push em `develop` dispara `.github/workflows/pr-develop-main.yml`, agora com
quatro jobs encadeados no mesmo workflow (proposta técnica da spec, 4.11:
"encadear criação/localização de PR e CI/CD no próprio workflow de push"):

```
garantir-pr ─┐
             ├─► publicar
verificar ─► construir ─┘
```

- **garantir-pr** — inalterado do ticket 17: garante/localiza o PR `develop -> main`.
- **verificar** — `make verificar` (ruff + mypy + pytest) e `make validar-sam`
  contra o SHA do push. Falha aqui impede `construir` e `publicar` por
  `needs:` (AC20).
- **construir** — `make construir-app` (SAM build, uma única vez), calcula um
  checksum SHA-256 do artefato e o publica como artefato do Actions
  (`artefato-<sha>`, retenção de 1 dia).
- **publicar** — dentro de um grupo de concorrência fixo
  (`producao-frase-diaria`, sem `cancel-in-progress`), o único job que assume
  papel AWS por OIDC:
  1. baixa o artefato de `construir` e confere o checksum;
  2. **reconsulta** se `develop` ainda aponta para este SHA, se o PR
     `develop -> main` ainda está aberto, e se `develop` inclui a base de
     `main` (`gh api .../compare/main...develop`) — só então prossegue;
  3. assume `frase-diaria-publicacao` por OIDC e registra uma implantação em
     andamento (GitHub Deployments API, ambiente `producao`);
  4. `make publicar-app-artefato VERSAO=<sha>` — publica exatamente o
     artefato baixado, sem reconstruir;
  5. diagnóstico pós-publicação: stack `UPDATE_COMPLETE`/`CREATE_COMPLETE`,
     `VersaoPublicada` da stack e `versao` de `GET /health` batendo com o
     SHA, as quatro funções `Active`/`Successful`, `POST /telegram/webhook`
     sem segredo devolvendo 200 (recusa silenciosa por design — não desperta
     nenhum comando), e os dois `AWS::Scheduler::Schedule` da stack
     completos;
  6. registra o resultado final na implantação — `success` só se o
     diagnóstico passou **e** o SHA ainda é o HEAD de `develop` nesse
     instante; `inactive` se o diagnóstico passou mas o SHA já foi superado
     por um push mais novo; `failure` se o diagnóstico reprovou. Só
     `failure` derruba o check do job.

## Decisão técnica

**Um único arquivo de workflow, não dois.** A spec propõe explicitamente essa
opção (4.11). Encadear evita reconsultar o PR duas vezes em lugares
diferentes e deixa a ordem declarada (`needs:`) refletir a ordem exigida
pela spec: SHA+PR → testes/lint/validação → build único → publicação.
`garantir-pr` e `verificar` rodam em paralelo (nenhum depende do outro para
existir); `construir` espera `verificar`; `publicar` espera os dois.

**Três grupos de concorrência, não um.** O `concurrency:` do workflow inteiro
do ticket 17 foi removido: um único grupo para os quatro jobs obrigaria
"publicar" a herdar o comportamento de cancelamento de "verificar", que é
errado nos dois sentidos. Agora:
- `pr-develop-main` (job `garantir-pr`) — inalterado, evita duas criações de
  PR simultâneas.
- `verificar-frase-diaria-<ref>` / `construir-frase-diaria-<ref>`, ambos
  `cancel-in-progress: true` — nenhum dos dois muta nada fora do runner
  efêmero; um push novo cancela a verificação do push anterior em vez de
  esperar ("apenas trabalhos sem mutação podem ser cancelados livremente",
  checklist do ticket 18).
- `producao-frase-diaria`, fixo (não por branch/ref) e **sem**
  `cancel-in-progress` — é a exclusão mútua real de produção. Cancelar um
  deploy no meio deixaria a stack pela metade; um push novo enfileira atrás
  deste, nunca o interrompe.

**Sem `environment:` do Actions no job `publicar` — decisão deliberada, não
esquecimento.** A trust policy de `frase-diaria-publicacao` (ticket 16,
`infra/bootstrap.yaml`) restringe o claim `sub` do OIDC a
`repo:.../ref:refs/heads/develop`. Declarar `environment: producao` no job
mudaria esse claim para o formato `repo:.../environment:producao`, e a
autenticação falharia contra a trust policy já publicada. "Registrar
publicação em andamento" (checklist do ticket 18) foi resolvido por outro
mecanismo: a **API de Deployments do GitHub** (`gh api .../deployments`),
que não depende da feature "Environments" do Actions nem altera o token
OIDC — só um rótulo `environment: "producao"` no corpo da requisição.

**"Invalidar a elegibilidade de merge da candidata anterior" não depende da
API de Deployments — depende do GitHub avaliar checks por SHA exato.**
Branch protection (ticket 21) sempre confere o check do commit que
atualmente é o HEAD do PR; o resultado de um SHA anterior nunca é
reaproveitado para um SHA diferente, mesmo que o anterior tenha sido
`success`. É esse mecanismo, nativo do GitHub e independente de qualquer
API adicional, que garante a invalidação. A API de Deployments serve só
como registro/auditoria de "o que foi publicado quando" — não é o
mecanismo de invalidação em si. (Nota de honestidade, registrada depois de
observar o comportamento real: eu esperava que `auto_inactive` marcasse a
implantação anterior como `inactive` ao registrar uma nova `success` — a
documentação da API descreve esse comportamento como padrão. Na prática,
com duas implantações reais `success` em sequência nesta sessão, a
primeira permaneceu `success`, nunca virou `inactive`. Não persegui a causa
— nenhum critério do ticket depende dela — mas registro que a frase
"invalida a elegibilidade de merge da candidata anterior" do checklist do
ticket 18 é satisfeita pelo mecanismo de checks por SHA acima, não pelo
`auto_inactive`.)

**AC22 tem duas camadas de proteção, uma da plataforma e uma do script.** A
camada da plataforma: GitHub só mantém *uma* execução "em progresso" e *uma*
"pendente" por grupo de concorrência — uma terceira execução que chegue
enquanto as duas primeiras existem cancela automaticamente a que estava
pendente (não a que já rodava). Isso já impede que uma publicação obsoleta
comece a rodar depois de ser substituída por um push mais novo, sem
nenhuma linha de script. A camada do script cobre o que a plataforma não
cobre: uma execução que **já estava rodando** quando um push mais novo
chegou terminaria normalmente (a plataforma nunca cancela o que já está em
progresso). O passo "Reconsultar PR aberto, SHA atual e base de main" e o
passo final "Registrar resultado da publicação" fecham essa lacuna,
reconsultando antes de publicar e de novo antes de marcar sucesso — nunca
presumindo ordem de chegada dos jobs, como a checklist exige.

**Verificação pós-publicação sem ampliar a policy do ticket 16.** A
verificação de agendamento não usa `scheduler:GetSchedule`/`ListSchedules`
(o papel de publicação não tem `ListSchedules`, e os dois `ScheduleV2` nunca
ganharam um `Name:` explícito em `infra/aplicacao.yaml`, então seus nomes
físicos não são previsíveis sem consultar). Em vez disso, a verificação usa
`cloudformation:ListStackResources` — já concedido — filtrando
`ResourceType=='AWS::Scheduler::Schedule'` e conferindo que os dois estão
`_COMPLETE`. Evita reabrir o IAM já revisado (e o achado de
escalonamento de privilégio já resolvido) do ticket 16 por uma necessidade
que uma permissão já concedida resolve igualmente bem.

**Diagnóstico nunca consome frase nem envia mensagem.** `GET /health` é
público e não aciona nenhum caso de uso de negócio. O smoke test do webhook
é um `POST` **sem** `X-Telegram-Bot-Api-Secret-Token`; por design
(`aplicacao_web.py`), a ausência do segredo é verificada antes de ler o
corpo ou despachar qualquer comando, e a resposta é sempre 200 — a
verificação confere exatamente esse 200, nunca chegando a acordar o worker.

**Achado real ao exercitar `make construir-app` pela primeira vez: o
Makefile só sabia construir duas das quatro funções.** A regra
`build-Funcao build-Worker:` não cobria `AgendadorDiario` nem
`Reconciliador` — um bug pré-existente, não introduzido por este ticket, que
nunca apareceu porque `make publicar-app` não era exercitado desde antes de
essas duas funções existirem (tickets 14/15). Rodar `sam build` de verdade
(não só ler o YAML) expôs isso na hora: `Make Failed: ... No rule to make
target 'build-AgendadorDiario'`. Corrigido ampliando a regra para as quatro
funções — elas compartilham o mesmo pacote (sem dependências por função), a
correção é a mesma regra cobrindo mais alvos, não lógica nova.

**`sam validate --lint` não exige credencial AWS — exercitado, não
presumido.** A pesquisa de segurança do projeto (`docs/pesquisa-agents-seguranca.md`)
tinha uma frase ambígua sobre isso. Testado localmente com
`AWS_CONFIG_FILE=/dev/null`, `HOME` isolado e nenhuma variável de credencial
no ambiente: `sam validate --lint` completou normalmente (cfn-lint roda
localmente). Por isso o job `verificar` não recebe `id-token: write` nem
qualquer credencial AWS — só o job `publicar` assume papel.

**Todo `${{ }}` de dado gerado pelo próprio job passa por `env:`, não vai
direto para `run:`.** Nenhum dos valores usados (checksum SHA-256,
`steps.*.outcome`, id de implantação) vem de PR/issue/branch/commit de
terceiro — não há sink de injeção real —, mas a skill
`github-actions-hardening` e o `AGENTS.md` pedem o padrão `env:` mesmo
quando o valor atual é seguro, como defesa em profundidade contra uma
mudança futura de formato. Aplicado nos quatro pontos encontrados.

## Publicação real — primeira execução

Após autorização explícita da usuária, o commit foi enviado para `develop`
de verdade (`gh run` `34260448739`). `garantir-pr`, `verificar` e `construir`
passaram; `publicar` **falhou** na conferência de checksum, antes de
qualquer credencial AWS ser configurada — ou seja, o mecanismo de segurança
funcionou exatamente como desenhado: nenhuma mutação chegou a acontecer.

**Causa raiz, achada comparando os dois checksums reais (não presumida):**
cada diretório de função (`Funcao/`, `Worker/`, `AgendadorDiario/`,
`Reconciliador/`) tinha um arquivo oculto `.lock` (vazio, deixado por `uv
pip install --target` como marcador de bloqueio do diretório de instalação).
`actions/upload-artifact@v7` descarta arquivos ocultos por padrão
(`include-hidden-files: false`, visível no log do passo). O checksum do job
`construir` foi calculado **antes** do upload, com o `.lock` presente; o
artefato realmente publicado **não o continha**; o recálculo em `publicar`,
sobre o artefato baixado, portanto não batia.

Confirmado passo a passo, não só lido no log: baixado o artefato exato do
run com `gh run download`, reproduzido localmente o mesmo checksum
`58ae56d8...` que o job `publicar` reportou (usando o mesmo prefixo de
caminho do script), e localizados os quatro `.lock` que só existiam no
build local, ausentes no artefato baixado.

**Correção:** o `.lock` não tem uso em runtime — é bookkeeping do `uv`, um
arquivo de 0 bytes. Adicionada ao `Makefile` (`build-Funcao ...`) a mesma
limpeza já existente para `__pycache__`, removendo `.lock` antes de o build
terminar. Reconstruído do zero localmente: zero itens ocultos remanescentes,
checksum estável. Isso resolve a causa, não o sintoma — não foi ativado
`include-hidden-files: true` no workflow, porque o artefato mais limpo
(sem bookkeeping de ferramenta) é preferível a manter um arquivo inútil só
para fazer o checksum bater.

**Achado adicional, não um bug:** os dois checksums diferentes não indicam
corrupção — o próprio Actions confirmou, de forma independente, que o ZIP
chegou intacto (`SHA256 digest of uploaded artifact` = `SHA256 digest of
downloaded artifact`, idênticos). A divergência era só entre o que o script
do projeto contava antes e depois do upload, nunca entre o que foi enviado e
o que chegou.

Corrigido, commitado (`git commit` separado) e reenviado para `develop`.

**Segunda execução real:** `garantir-pr`, `verificar` e `construir`
passaram; `publicar` falhou de novo, agora em "Configurar credenciais AWS
(OIDC)": `Not authorized to perform sts:AssumeRoleWithWebIdentity`, depois
de 12 tentativas com backoff. A stack `frase-diaria-app` **não foi tocada**
— o erro acontece antes de qualquer chamada `sam deploy`.

**Causa raiz, confirmada contra um token real, não contra documentação
parafraseada.** A pesquisa de segurança do projeto já registrava a
nuance ("repositórios criados depois de 2026-07-15 usam, por padrão, `sub`
imutável com IDs") e mandava "confirmar o formato real da claim e nunca
inventá-lo" — mas ninguém tinha exercitado isso contra um `AssumeRoleWithWebIdentity`
de verdade até agora, porque nenhum workflow com `id-token: write` existia
antes do ticket 18. Este repositório foi criado em 2026-09-06 (depois do
corte). Em vez de confiar numa paráfrase de doc para mudar uma trust
policy IAM, adicionei um passo de debug temporário ao job `publicar` que
busca o próprio token OIDC da execução (via `ACTIONS_ID_TOKEN_REQUEST_URL`/
`ACTIONS_ID_TOKEN_REQUEST_TOKEN`, já disponíveis com `id-token: write`) e
imprime só os claims decodificados — nunca o token inteiro. O `sub` real
emitido:

```
repo:soamazyng@443219/frase-diaria-telegram@1359588301:ref:refs/heads/develop
```

— o formato imutável baseado em IDs, exatamente como a pesquisa alertava,
divergindo do formato `repo:soamazyng/frase-diaria-telegram:ref:refs/heads/develop`
que a trust policy do ticket 16 assumia. `aud` continuava `sts.amazonaws.com`,
sem mudança.

**Correção em `infra/bootstrap.yaml`:** o parâmetro único `RepositorioGitHub`
("owner/repo") virou quatro parâmetros — `ProprietarioGitHub`,
`IdDoProprietarioGitHub`, `NomeDoRepositorio`, `IdDoRepositorio` — e a
condição `sub` das duas roles (`PapelDePublicacao`, `PapelDeInfraestrutura`)
passou a interpolar `${ProprietarioGitHub}@${IdDoProprietarioGitHub}/${NomeDoRepositorio}@${IdDoRepositorio}`.
Revisado por change set antes de aplicar: `Modify`/`Replacement: False` nas
duas roles, nada mais na stack afetado (confirmado, não presumido). Aplicado
na AWS real (`aws cloudformation execute-change-set`), `UPDATE_COMPLETE`, e
a trust policy publicada conferida de volta contra o `sub` real capturado
acima — batem. O passo de debug foi removido do workflow depois de cumprir
seu propósito (não fica no pipeline definitivo).

**Por que isso não é scope creep do ticket 18, apesar de tocar um arquivo do
ticket 16:** sem essa correção, o mecanismo central do ticket 18 —
publicação via OIDC — não funciona em nenhuma circunstância; não é uma
melhoria opcional, é um defeito bloqueante descoberto ao exercitar o
pipeline de verdade pela primeira vez, da mesma natureza do bug do `.lock`
acima.

## Terceira execução real — OIDC funcionou, faltava `uv` no job

Com a trust policy corrigida, a autenticação OIDC passou (progresso real:
esta foi a primeira vez que o job `publicar` avançou além do
`configure-aws-credentials`). Falhou em seguida em `sam deploy (artefato já
construído)`: `/bin/sh: 1: uvx: not found`, `make: *** [Makefile:85:
publicar-app-artefato] Error 127`. **Nenhuma mutação na stack ocorreu** — o
erro acontece antes de qualquer chamada real à AWS de deploy.

Causa: o job `publicar` nunca teve o passo `astral-sh/setup-uv`, só
`verificar` e `construir` o tinham. `make publicar-app-artefato` depende da
variável `SAM` do Makefile (`uvx --from aws-sam-cli sam`), que precisa de
`uv`/`uvx` no runner. Um descuido puro e simples na primeira versão do
workflow, só visível rodando de verdade — `actionlint`/`shellcheck` não
detectam ausência de uma ferramenta de runtime, só sintaxe.

O tratamento de falha do próprio pipeline funcionou como desenhado: o passo
final "Registrar resultado da publicação" (com `if: always()`) rodou mesmo
com o deploy falho, viu `DESFECHO_DO_DIAGNOSTICO=skipped` (o diagnóstico
nunca chegou a rodar) e registrou `state=failure` na implantação do GitHub
— exatamente o comportamento que a checklist do ticket 18 exige para uma
publicação malsucedida.

Corrigido adicionando `astral-sh/setup-uv` ao job `publicar`, no mesmo
ponto em que os outros dois jobs o têm. `actionlint`/`shellcheck` revalidados.

## Quarta e quinta execuções reais — dois gaps de IAM na stack de aplicação

Com OIDC e `uv` corrigidos, `sam deploy` chegou a rodar de verdade pela
primeira vez. Faltava só permissão para o bucket gerenciado pelo SAM
(`aws-sam-cli-managed-default`, criado no ticket 03): `AccessDenied` em
`cloudformation:CreateChangeSet` sobre aquela stack. Corrigido dando ao
papel de publicação acesso escopado por nome exato a essa stack e ao seu
bucket (sem `CreateStack`/`UpdateStack` — o papel só confirma o estado de
um recurso que já existe, nunca pode recriá-lo ou alterá-lo). Aplicado por
change set revisado (`Modify`, sem substituição) — desta vez o classificador
de segurança do Claude Code pausou a execução automática por ser mais uma
mutação de IAM em sequência; confirmado explicitamente pela usuária antes
de aplicar.

Com essa permissão, o `sam deploy` real avançou até mudar a stack
`frase-diaria-app` de verdade — e falhou de um jeito novo, dentro do
`CREATE` dos dois recursos `AWS::Scheduler::Schedule`
(`AgendadorDiarioAgendamento`, `ReconciliadorVarredura`): `AccessDenied` em
`scheduler:GetSchedule`. À primeira vista parecia faltar essa ação na
policy — mas ela **já estava lá** (`AgendamentosDaAplicacao`, ticket 16). O
problema real: a policy escopa `Resource` para
`schedule/default/${Prefixo}-*`, e como `infra/aplicacao.yaml` nunca deu um
`Name:` explícito aos dois `ScheduleV2`, o CloudFormation gerou os nomes
físicos `AgendadorDiarioAgendamento`/`ReconciliadorVarredura` — **sem** o
prefixo `frase-diaria-`. O IAM sempre esteve certo; o template de aplicação
é que nunca produzia um nome que batesse com ele. Isso nunca tinha
aparecido porque estas duas funções nunca tinham sido publicadas de
verdade antes (bloqueadas pelo mesmo bug do Makefile corrigido no início
deste ticket) — outra instância do mesmo padrão: bug adormecido, exposto só
ao exercitar a coisa real pela primeira vez.

**A stack fez rollback automático e limpo** (`UPDATE_ROLLBACK_COMPLETE`,
confirmado via `aws cloudformation describe-stacks`) — nenhum recurso
ficou pela metade. Conferido também, não presumido: `aws scheduler
list-schedules` não mostra nenhum agendamento órfão (o `CreateSchedule`
subjacente nunca chegou a persistir, ou o próprio CloudFormation limpou).

**Correção em `infra/aplicacao.yaml`, não no IAM desta vez:** os dois
`ScheduleV2` ganharam `Name: !Sub "${Prefixo}-agendador-diario"` e
`Name: !Sub "${Prefixo}-reconciliador"` — passa a bater com o escopo que a
policy do ticket 16 sempre teve, sem alargar nenhuma permissão. `sam
validate --lint` revalidado. Esta é uma mudança normal de aplicação, que o
próprio pipeline publica no próximo push — não uma mutação manual de infra
fora do fluxo do ticket 18.

## Sexta execução real — sucesso completo

Com os dois `Name:` adicionados, o pipeline rodou do início ao fim sem
nenhuma falha: `garantir-pr` → `verificar` → `construir` → `publicar`, os
quatro jobs verdes. `sam deploy` atualizou `frase-diaria-app` de verdade
(`UPDATE_COMPLETE`), publicando pela primeira vez as quatro funções
completas — inclusive `AgendadorDiario` e `Reconciliador`, que nunca tinham
sido publicadas de verdade antes (bloqueadas pelo bug do Makefile corrigido
no início deste ticket). O diagnóstico pós-publicação aprovou saúde, versão,
as quatro funções, o smoke test do webhook e os dois agendamentos. A
implantação foi registrada `success` na API de Deployments do GitHub.

Conferido diretamente contra a AWS e o GitHub reais, não só pelo log do
job:

```
gh api .../deployments/6336765673/statuses  →  state: success
GET /health                                 →  {"situacao":"ok","versao":"0cd19f86fcf5d1b65f6d9900db63fd8cda71fdb0",...}
```

`versao` bate exatamente com o SHA do commit publicado — AC21 exercitado
contra o sistema real, não presumido.

## Verificação

**Exercitado de verdade, não só lido:**
- `make validar-sam` e `make construir-app` rodados localmente, do zero
  (`.aws-sam` removido antes). Build teve que ser corrigido (achado acima) e,
  depois da correção, teve sucesso real para as quatro funções.
- Artefato conferido: `_pydantic_core.cpython-313-aarch64-linux-gnu.so` — ELF
  ARM aarch64, não macOS (a armadilha documentada em `rules.md`).
- Script de checksum (o mesmo usado nos jobs `construir`/`publicar`) rodado
  contra o artefato real, produzindo um SHA-256 estável.
- `sam validate --lint` exercitado sem nenhuma credencial AWS no ambiente
  (`AWS_CONFIG_FILE=/dev/null`, `HOME` isolado) — completou, confirmando que
  o job `verificar` realmente não precisa de OIDC.
- Sintaxe e semântica do workflow: `yaml.safe_load` (via ambiente `uv`
  efêmero) e `actionlint` com `shellcheck` habilitado (ambos baixados
  isoladamente no diretório de scratchpad da sessão, não instalados no
  sistema) — zero achados nas duas rodadas, antes e depois dos ajustes de
  hardening.

**Publicação real, autorizada explicitamente pela usuária, executada em seis
rodadas até verde** (`git log` de `c2e4e88` a `0cd19f8`, todas nesta sessão,
2026-09-08). Cada falha real corrigida em sequência, documentada acima com
o log/evidência que a comprovou — nenhuma delas simulada ou presumida:

1. Checksum: `.lock` do `uv` descartado por `include-hidden-files: false`.
2. OIDC: `sub` no formato imutável, confirmado contra token real.
3. `uvx` ausente no job `publicar` (faltava `setup-uv`).
4. IAM: papel de publicação sem acesso ao bucket gerenciado pelo SAM.
5. IAM/nomeação: `ScheduleV2` sem `Name:` gerava nomes fora do escopo IAM.
6. **Sucesso completo** — os quatro jobs verdes, `sam deploy` real,
   diagnóstico aprovado, implantação `success` na API de Deployments,
   `GET /health` real confirmando `versao` = SHA publicado.

Duas mutações de IAM (trust policy e permissão de bucket) foram aplicadas
manualmente via `aws cloudformation execute-change-set`, cada uma revisada
por change set antes (`Modify`, sem substituição) e confirmada
explicitamente pela usuária — o classificador de segurança do Claude Code
pausou a segunda para confirmação, por ser mutações de IAM em sequência. A
correção do `ScheduleV2` (aplicação, não infra de confiança) fluiu pelo
próprio pipeline, sem mutação manual.

**Atualização depois de um segundo push real:** uma segunda publicação
`success` aconteceu logo em seguida (documentação, sem mudança de código),
permitindo observar o `auto_inactive` de verdade — e ele **não** marcou a
implantação anterior como `inactive`; ela permanece `success` no histórico.
Corrigida a alegação anterior neste documento (ver Decisão técnica): a
garantia de "invalidar a elegibilidade de merge da candidata anterior" não
vem daí, vem do GitHub sempre avaliar o check do SHA atual do PR, nunca de
um SHA anterior — mecanismo que independe do `auto_inactive` e que
continua garantido.

## Review

Não se aplica `/code-review` de Standards/Spec em dois eixos nem
`security-review` de aplicação — não há código Python nesta entrega (só
`Makefile`, YAML e este documento). Consultada a skill local
`python-clean-code`: as regras específicas de Python (F1-F4, P1-P3, tipagem)
não se aplicam a nenhum arquivo tocado; dos princípios gerais, aplicados
deliberadamente **G5** (DRY — `STACK_APLICACAO` extraído para não repetir o
nome da stack nas duas chamadas de diagnóstico) e **C1-C4** (comentários
justificam decisão/restrição — por que não há `environment:`, por que
`scheduler:ListSchedules` foi evitado — nunca descrevem o óbvio). Rodada a
skill `github-actions-hardening` (dedicada a este tipo de arquivo, como nos
tickets 16/17): nenhum trigger privilegiado, nenhum sink de injeção real
(gatilho é só `push`, que já exige acesso de escrita), `permissions: {}` no
topo com elevação mínima só por job, `id-token: write` só em `publicar`,
todas as `uses:` de terceiro fixadas por SHA completo (conferido contra
`releases/latest` de cada repositório, não copiado de memória), nenhum
segredo tocado. Achado de estilo/defesa em profundidade — quatro `${{ }}`
de valores internos direto em `run:` — corrigido roteando por `env:` (ver
Decisão técnica).

## Próximo passo

Ticket concluído: pipeline publicou de verdade, com diagnóstico aprovado
contra a AWS real e implantação registrada `success` no GitHub. O próximo
ticket elegível por dependência é o **19 — Recuperação da versão
anterior**, que passa a ter algo real para recuperar em caso de falha —
inclusive os cinco incidentes reais desta sessão (checksum, OIDC, `uv`
ausente, dois gaps de IAM) são material direto para desenhar os cenários de
falha que aquele ticket precisa cobrir.
