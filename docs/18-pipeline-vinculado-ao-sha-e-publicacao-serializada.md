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

**A API de Deployments também resolve "invalidar a elegibilidade de merge
da candidata anterior" de graça.** Por comportamento documentado da API, ao
registrar o status `success` de uma nova implantação, o GitHub marca
automaticamente a implantação `success` anterior do mesmo ambiente como
`inactive` (`auto_inactive`, ligado por padrão). Não foi escrita nenhuma
lógica própria para isso — é o comportamento nativo da API sendo aproveitado
pelo desenho.

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

Corrigido, commitado (`git commit` separado) e reenviado para `develop`; a
segunda execução real está descrita no restante deste documento.

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

**Não exercitado nesta sessão — pendente de autorização explícita:** o job
`publicar` nunca rodou contra o GitHub/AWS reais. Isso exigiria um push de
verdade para `develop`, que aciona `sam deploy` em produção pelo papel
`frase-diaria-publicacao` assumido por OIDC — uma mutação real de produção
que o `AGENTS.md` exige autorização explícita para executar, e que não foi
pedida nesta tarefa. A lógica foi revisada exaustivamente (concorrência,
reconsulta de atualidade, checksum, diagnóstico, API de Deployments) e
validada estruturalmente (lint, sintaxe, achados de hardening corrigidos),
mas **o primeiro deploy real pelo pipeline ainda precisa ser observado** —
inclusive para confirmar contra o GitHub real o comportamento de
`auto_inactive` documentado, e contra a AWS real o diagnóstico pós-deploy
(inclusive possível instabilidade de propagação entre `UPDATE_COMPLETE` da
stack e `LastUpdateStatus: Successful` de cada função, que os `--retry` do
`curl` amenizam só para `/health`, não para os demais checks).

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

O código está completo e localmente validado, mas a entrega deste ticket só
fecha depois que o pipeline publicar de verdade pela primeira vez — o que
exige um push autorizado para `develop` (mutação real de produção via OIDC).
Até essa autorização e essa execução real, o item da issue permanece aberto
apesar do código pronto. Depois de observada uma publicação real bem-sucedida
(ou de corrigir o que ela revelar), o próximo ticket elegível por dependência
é o **19 — Recuperação da versão anterior**.
