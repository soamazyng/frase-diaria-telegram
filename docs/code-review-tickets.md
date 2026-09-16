# Auditoria de code-review dos tickets

Data da auditoria: 2026-09-07.

Este documento consolida o estado dos tickets 01–22 e separa duas perguntas:

1. há evidência histórica de que um code-review foi executado; e
2. o diff passa hoje nos eixos independentes **Standards** e **Spec**.

Uma mensagem de commit que diz “correções vindas do code-review” é evidência
declarativa de que houve revisão durante a implementação. Quando as correções e essa
declaração estão no mesmo commit, ela **não prova** que um novo review ocorreu depois da
última correção. Por isso nenhum desses casos recebe um “OK final pós-correção”. Para
certificar essa ordem temporal seria necessário um registro posterior e independente.

Não reproduza neste documento valores encontrados no histórico. IDs, endpoints e demais
identificadores operacionais aparecem apenas como categorias e localizações.

## Estado consolidado

| Ticket | Estado do trabalho | Evidência histórica de code-review | Auditoria atual |
|---|---|---|---|
| 01 | Concluído administrativamente | Não localizada; entrega documental e policy de bootstrap, sem implementação de código a certificar | Não auditado como diff de código |
| 02 | Concluído | Declarada na mensagem completa de `<COMMIT_SHA>`; não comprova re-review final pós-correção | Spec: OK; Standards: achado sob regra nova |
| 03 | Concluído | Não localizada nas mensagens completas do intervalo | Achados em Standards e Spec |
| 04 | Concluído | Não localizada nas mensagens completas do intervalo | Achados em Standards e Spec |
| 05 | Concluído | Declarada na mensagem completa de `<COMMIT_SHA>`; não comprova re-review final pós-correção | Achados em Standards e Spec |
| 06 | Concluído | Declarada na mensagem completa de `<COMMIT_SHA>`; `<COMMIT_SHA>` registra exercício AWS, não um re-review final | Spec: OK no escopo; Standards: achados, incluindo débito conhecido |
| 07 | Em implementação no diretório de trabalho | Review executado no diretório de trabalho do ticket | Spec: OK; Standards: sem achados de alta confiança |
| 08 | Em implementação no diretório de trabalho | Review executado no diretório de trabalho do ticket | Spec: OK; Standards: sem achados de alta confiança |
| 09 | Concluído | Review executado no diretório de trabalho do ticket | Spec: OK após correção; Standards: 2 achados, ambos corrigidos |
| 10 | Concluído (wiring fechado pelo ticket 11) | Review executado no diretório de trabalho do ticket | Spec: OK; Standards: 2 achados, ambos corrigidos |
| 11 | Concluído | Review executado no diretório de trabalho do ticket (2 rodadas — a 1ª não viu os arquivos novos, untracked) | Spec: OK após correção; Standards: 4 achados, todos corrigidos |
| 12 | Concluído | Review executado no diretório de trabalho do ticket | Spec: OK; Standards: OK |
| 13 | Pendente | Não aplicável ainda | Pendente |
| 14 | Pendente | Não aplicável ainda | Pendente |
| 15 | Pendente | Não aplicável ainda | Pendente |
| 16 | Pendente | Não aplicável ainda | Pendente |
| 17 | Pendente | Não aplicável ainda | Pendente |
| 18 | Pendente | Não aplicável ainda | Pendente |
| 19 | Pendente | Não aplicável ainda | Pendente |
| 20 | Pendente | Não aplicável ainda | Pendente |
| 21 | Pendente | Não aplicável ainda | Pendente |
| 22 | Pendente | Não aplicável ainda | Pendente |
| 26 | Concluído em 2026-09-16 | Review em dois agentes sobre os arquivos da task, base `<COMMIT_SHA>`, seguido de re-review após correção | Standards: OK; Spec: OK; 433 testes e gate completo aprovados |

### Atualização do ticket 26 — 2026-09-16

O review da conclusão encontrou, nos dois eixos, uma incerteza persistida que podia
ser perdida no encerramento por falha permanente ou prazo, liberando a frase para
novo sorteio. Dois casos de regressão falharam antes da correção e passaram depois:
o encerramento mantém `INCERTO` e consumo com ressalva. Re-review independente dos
trechos corrigidos: **Standards OK; Spec OK**, sem achados pendentes. O gate final
passou com 433 testes, Ruff, formatação e mypy. Detalhes, limitações de histórico e
aceite real pendente em `docs/26-status-por-destinatario.md`.

O ticket 01 verificou condições de conta, custo e permissões e entregou documentação e
`docs/aws-policy-bootstrap.json`. Isso não equivale a uma implementação de código nem a
um code-review comprovado; não se deve inferir um “OK” técnico apenas porque a policy
existe.

## Evidência histórica e testes

As mensagens completas dos commits, e não apenas os títulos, sustentam as classificações
abaixo:

- **Ticket 02 — `<COMMIT_SHA>`:** declara “correções vindas do code-review” e enumera quatro
  correções. Como a declaração e as correções pertencem ao mesmo commit, o review final
  depois da última alteração não está comprovado.
- **Ticket 03 — `<COMMIT_SHA>`:** descreve implementação e verificações AWS, sem declarar
  code-review.
- **Ticket 04 — `<COMMIT_SHA>` e `<COMMIT_SHA>`:** descrevem implementação, correção de configuração
  e exercício AWS, sem declarar code-review.
- **Ticket 05 — `<COMMIT_SHA>`:** declara “correções vindas do code-review”, enumera sete
  correções e encaminha três achados aos tickets 08, 09 e 14. Não há evidência separada
  de re-review depois dessas correções.
- **Ticket 06 — `<COMMIT_SHA>`:** declara “correções vindas do code-review” e enumera cinco
  correções. O commit posterior `<COMMIT_SHA>` registra o exercício AWS e uma limitação
  encaminhada ao ticket 14, mas não declara novo code-review.

Os snapshots históricos foram exercitados com o ambiente virtual atual, sem reconstruir
o `uv.lock` de cada commit. Portanto os números abaixo demonstram compatibilidade com as
dependências atualmente instaladas, não uma reprodução hermética do ambiente histórico.

| Ticket | Resultado no snapshot |
|---|---:|
| 02 | 21 testes passaram |
| 03 | 21 testes passaram |
| 04 | 72 testes passaram |
| 05 | 123 testes passaram |
| 06 | 170 testes passaram |

## Standards

Legenda temporal:

- **Vigente:** regra já documentada no commit ou na base do ticket; pode evidenciar falha
  do review histórico.
- **Nova:** regra introduzida depois, no `AGENTS.md` atual; vale para correções futuras,
  mas não prova que o review histórico falhou.
- **Baseline atual:** smell heurístico do skill atual; é julgamento, não violação dura.

Salvo indicação contrária, caminhos e linhas desta seção pertencem ao snapshot final de
cada ticket: 02 em `<COMMIT_SHA>`, 03 em `<COMMIT_SHA>`, 04 em `<COMMIT_SHA>`, 05 em `<COMMIT_SHA>` e 06 em
`<COMMIT_SHA>`. Eles não devem ser interpretados como linhas do diretório de trabalho atual.

### Ticket 02

- **Nova — segurança/alta:**
  `contextIA/Spec-Frase-Diaria-Telegram.md:19-20` versionou URLs concretas do Notion e
  seus IDs. O `AGENTS.md` atual classifica IDs e URLs operacionais como sensíveis e exige
  marcadores fictícios. Na época, a própria spec continha essas URLs e o `CLAUDE.md`
  protegia explicitamente tokens, `chat_id` e URLs assinadas; isto não comprova falha do
  review histórico.
- **Baseline atual:** OK; o scaffold, as portas e os pacotes eram exigidos pelo ticket.

### Ticket 03

- **Vigente — segurança/alta:** no snapshot `<COMMIT_SHA>`,
  `infra/aplicacao.yaml:76-88` concede à Lambda que só atendia `/health` ações DynamoDB
  de leitura, escrita, exclusão, consulta e transação. Isso viola a spec 4.9 e o próprio
  ticket 03, que exigem permissões específicas por função; o comentário do YAML também
  promete somente ações usadas.
- **Nova — segurança/média:** `CLAUDE.md:40` e
  `docs/03-publicacao-manual.md:26,45` registram ID de conta e endpoint operacionais. A
  classificação inequívoca desses valores como sensíveis veio no `AGENTS.md` posterior;
  os valores são deliberadamente omitidos aqui.
- **Baseline atual:** OK.

### Ticket 04

- **Vigente — segurança/alta:** no snapshot `<COMMIT_SHA>`,
  `src/frase_diaria/aplicacao/receber_comando.py:55-61` interpreta e extrai a conversa
  antes de validar o segredo. Isso viola a ordem explícita segredo → tipo → `chat_id` do
  ticket 04. O teste e a documentação afirmam essa ordem, mas não a demonstram.
- **Vigente em parte; ampliada pela regra nova — segurança/alta:** `CLAUDE.md:46-48`
  versionou um `chat_id` real apesar de o `CLAUDE.md` anterior já dizer que esse valor
  ficava fora do Git. O mesmo intervalo usou IDs operacionais nas fixtures
  `tests/aplicacao/test_receber_comando.py:17`,
  `tests/dominio/test_autorizacao.py:17-18`,
  `tests/persistencia/test_repositorio_de_comandos.py:24`,
  `tests/telegram/test_atualizacao.py:15` e `tests/telegram/test_canal.py:39`, além de um
  endpoint concreto em `docs/04-webhook-telegram.md:47`. A proibição explícita desses
  casos adicionais veio no `AGENTS.md` posterior. Valores omitidos.
- **Nova — segurança/média:** `src/frase_diaria/telegram/canal.py:46` incorpora o campo
  `description` de uma resposta externa na exceção. O `AGENTS.md` atual exige omitir
  corpos e respostas de integrações; a regra da época cobria expressamente token e URL.
- **Vigente — operação/média:**
  `src/frase_diaria/infraestrutura/composicao.py:25-27` afirma que containers absorvem
  rotação sem intervenção, enquanto o `CLAUDE.md` do mesmo commit diz que republicar é
  necessário para efeito imediato. A contradição pode manter credencial antiga ativa.
- **Vigente — IAM/média:** `infra/aplicacao.yaml:102-106` concede três ações SSM, mas o
  código usa apenas `GetParametersByPath`, contrariando permissões específicas.
- **Baseline atual — julgamento:** possível Primitive Obsession em
  `dominio/autorizacao.py:20-23`, onde `Conversa.tipo: str` representa um conjunto fechado
  que decide autorização.

### Ticket 05

- **Vigente em parte; ampliada pela regra nova — segurança/alta:** no snapshot `<COMMIT_SHA>`,
  `aplicacao/processar_pedido.py:54,116-121` e
  `infraestrutura/worker_handler.py:28-30` registram identidades persistentes e
  `repr(erro)`. A spec e o `rules.md` já exigiam erro sanitizado; a classificação
  explícita de IDs e payloads como sensíveis veio depois. O `repr(erro)` é falha sob o
  padrão histórico; expor identidades também viola claramente o padrão atual.
- **Vigente — arquitetura/média:**
  `src/frase_diaria/aplicacao/processar_pedido.py:9,111` faz o caso de uso
  depender da exceção concreta `telegram.canal.ErroDoTelegram`, apesar de o canal ser uma
  porta. Isso contraria a independência de integrações prevista na spec 4.1 e no
  `CLAUDE.md`.
- **Vigente — IAM/alta:** `infra/aplicacao.yaml:85-112,148-150` entrega à função HTTP e ao
  worker o mesmo conjunto amplo de ações DynamoDB e todos os parâmetros do prefixo. As
  funções não precisam das mesmas ações nem dos mesmos segredos.
- **Nova — segurança/média:** novos testes reutilizam como `chat_id` um identificador
  operacional real em `tests/aplicacao/test_processar_pedido.py:18`,
  `tests/dominio/test_pedido.py:14`,
  `tests/persistencia/test_repositorio_de_pedidos.py:20` e
  `tests/telegram/test_canal.py:43`. A vedação explícita de IDs reais em testes veio no
  `AGENTS.md` posterior; o valor é omitido aqui.
- **Baseline atual — julgamento:** possível Primitive Obsession em `Pedido.identidade` e
  nos parâmetros `pedido: str` e `resultado: str`.

### Ticket 06

- **Vigente — concorrência/alta; conhecido e diferido:** no snapshot `<COMMIT_SHA>`,
  `persistencia/ciclos.py:56` grava o ciclo inteiro sem condição, e
  `persistencia/reserva.py:26-43` só condiciona a existência do pedido, sem versão do
  ciclo. Dois workers podem sobrescrever reserva ou consumo. Isso viola a spec 4.6/AC03,
  mas `docs/06-ciclos-e-selecao.md` e o ticket 09 registraram explicitamente o débito; ele
  não ficou oculto pelo review.
- **Vigente de forma implícita; explicitada pela regra nova — arquitetura/média:**
  `src/frase_diaria/dominio/selecao.py:3` faz o domínio importar
  `aplicacao.portas.Sorteio`, invertendo a
  direção esperada. A separação de responsabilidades já existia; a regra direta de que a
  aplicação define portas foi escrita depois no `AGENTS.md`.
- **Vigente em parte; ampliada pela regra nova — segurança/média:**
  `aplicacao/processar_pedido.py:77,93,174,193-196` inclui identidades em logs/exceções e
  persiste `repr(erro)`. O `repr(erro)` já colidia com `rules.md`; a proteção explícita de
  IDs veio no `AGENTS.md` posterior.
- **Nova — segurança/média:** `tests/persistencia/test_reserva_transacional.py:23`
  adiciona um ID operacional real como `chat_id`; a vedação explícita é posterior.
- **Baseline atual — julgamento:** possível Primitive Obsession nos vários
  `frozenset[str]` e parâmetros `frase: str` de `src/frase_diaria/dominio/ciclo.py`.

### Ticket 09

- **Achado corrigido — concorrência/alta:** `aplicacao/processar_pedido.py` não avançava
  a variável local `versao_ciclo` em memória depois que `reserva.efetivar` persistia a
  versão seguinte, então toda entrega comum (sem concorrência real) caía num conflito de
  versão espúrio ao gravar o consumo, mascarado pela retentativa. Corrigido incrementando
  `versao_ciclo` logo após a reserva; regressão coberta por
  `tests/aplicacao/test_processar_pedido.py::test_reservar_e_entregar_na_mesma_execucao_nao_gera_conflito_de_versao`.
- **Achado corrigido — projeto/média:** `_retentar_no_ciclo` desistia em silêncio após 5
  tentativas, arriscando (sob contenção real) deixar o consumo de uma frase sem persistir
  enquanto o pedido já está terminal. A margem foi ampliada para 20 — a operação é local e
  barata, sem chamada ao Telegram, então o custo de mais tentativas é desprezível frente ao
  risco de esgotá-las.

Achados de uma revisão posterior, já com o ticket commitado, sobre o diff acumulado desde
`main` (não só o diff deste ticket) — ver `docs/09-lease-escritas-condicionais-e-concorrencia.md`:

- **Achado corrigido — concorrência/alta:** `pedidos.py::assumir_lease` usava
  `lease_dono < :seq` (estrito); um retry automático do SDK reafirmando a própria
  tentativa era recusado como se fosse de outro executor. Corrigido para `<=`;
  regressão em `test_reassumir_o_proprio_lease_e_idempotente`.
- **Achado corrigido — projeto/baixa:** `_retentar_no_ciclo` relia sem dispersão entre
  tentativas. Adicionado jitter pequeno (até 20 ms).
- **Achado aceito, não corrigido — duplicação/baixa:** a tradução de exceção do boto3
  para `ConflitoDeConcorrencia` se repete em cinco pontos com variações genuínas o
  bastante para que unificá-las agora arriscasse introduzir nova assimetria.

### Ticket 10

A primeira rodada de review não viu os arquivos novos (eram *untracked*, fora do
diff); uma segunda rodada, depois de `git add`, encontrou e confirmou dois
defeitos, ambos corrigidos antes do commit — ver
`docs/10-sincronizacao-com-notion.md`:

- **Achado corrigido — corretude/alta:** `notion/leitura.py::_ler_discussoes` não
  capturava `ErroDoNotion`; um erro do Notion ao buscar discussões que não fosse
  403 escapava cru em vez de virar `SincronizacaoIncompleta`, quebrando o contrato
  documentado no resto do módulo.
- **Achado corrigido — corretude/alta:** `notion/cliente.py::_paginar` entrava em
  loop infinito se a API respondesse `has_more: true` sem `next_cursor`.
  Confirmado reproduzindo o loop de verdade (com timeout de shell) antes de
  corrigir.

### Ticket 11

A mesma situação do ticket 10 se repetiu: a primeira rodada não viu os arquivos
novos (untracked); uma segunda, depois de `git add`, encontrou e confirmou quatro
defeitos, todos corrigidos antes do commit — ver
`docs/11-snapshot-duravel-cache-e-fallback.md`:

- **Achado corrigido — concorrência/alta:** `processar_pedido.py::_processar`
  mutava `pedido` para `frase_reservada=None` antes de tentar a transação de
  troca de frase excluída. Um conflito de concorrência nessa transação faria
  persistir esse `pedido` já liberado enquanto o ciclo persistido continuava com
  a frase antiga reservada — órfã, sem nenhum pedido para liberá-la depois,
  travando o ciclo para sempre. Corrigido separando o `pedido` que reflete o
  persistido da tentativa em memória.
- **Achado corrigido — corretude/média:** `persistencia/colecao.py::substituir`
  não persistia `ColecaoValida.diagnosticos`, contrariando o próprio domínio
  ("precisam ficar visíveis").
- **Achado corrigido — concorrência/média:** o mesmo `substituir` gravava
  incondicionalmente; duas sincronizações concorrentes terminando fora de ordem
  deixariam a mais antiga sobrescrever a mais nova, ressuscitando momentaneamente
  uma frase já excluída.
- **Achado corrigido — robustez/média:** `infraestrutura/fonte_notion.py::_para_frase`
  (o placeholder de texto plano) podia gerar uma parte vazia e derrubar
  `listar()` para a coleção inteira por causa de uma única frase sem rich text.

## Spec

Este eixo avalia somente requisitos ausentes ou parciais, scope creep e requisitos
implementados incorretamente. Itens explicitamente destinados a tickets posteriores não
são reclassificados como falha do ticket anterior.

### Ticket 02 — OK

Nenhum requisito ausente/parcial, scope creep funcional ou requisito implementado
incorretamente.

### Ticket 03

- **Implementação incorreta:** o ticket exige “permissões IAM específicas por função”
  (`.scratch/frase-diaria-telegram/issues/03-publicacao-manual-sam-health-na-aws.md:9`;
  spec 4.9). A única Lambda só
  executava `/health`, mas recebeu todas as operações DynamoDB descritas em
  `infra/aplicacao.yaml:76-88` no snapshot `<COMMIT_SHA>`.
- **Ausente/parcial:** nenhum outro.
- **Scope creep:** nenhum outro.

### Ticket 04

- **Implementação incorreta:** atualizações irrelevantes retornam antes de qualquer
  autenticação em `src/frase_diaria/aplicacao/receber_comando.py:55-65` no snapshot
  `<COMMIT_SHA>`. Isso
  contradiz “atualizações irrelevantes já validadas” (ticket 04, linha 16; spec 4.7) e a
  ordem exigida no ticket 04, linha 9.
- **Requisito parcial:** se o envio da ajuda falha depois de registrar o update, a
  reentrega encontra o registro e retorna antes de tentar enviar novamente
  (`src/frase_diaria/aplicacao/receber_comando.py:67-80`). Assim `/start` e comando
  desconhecido podem
  nunca receber a ajuda exigida nas linhas 10–11 do ticket.
- **Scope creep de privilégio:** `infra/aplicacao.yaml:100-114` concede duas ações SSM
  além de `GetParametersByPath`, a única utilizada, contrariando a spec 4.9.

### Ticket 05

- **Implementação incorreta:** a sanitização exigida no ticket 05, linha 14, e na spec
  4.8 não cobre exceções inesperadas do canal.
  `src/frase_diaria/aplicacao/processar_pedido.py:114-122` grava `repr(erro)` e registra
  traceback bruto; `src/frase_diaria/telegram/canal.py:64-65` também aceita a descrição
  bruta retornada pela Bot API.
- **Scope creep de privilégio:** o novo worker herda leitura de todo o prefixo de segredos
  e carrega todos os parâmetros embora use apenas o token do bot
  (`infra/aplicacao.yaml:145-150`;
  `src/frase_diaria/infraestrutura/composicao.py:71-77`). Isso contraria permissões
  específicas por função da spec 4.9.
- **Ausente/parcial:** nenhum outro.

### Ticket 06 — OK no escopo

Nenhum requisito próprio do ticket está ausente/parcial, fora do escopo ou implementado
incorretamente, consideradas as dependências planejadas abaixo.

### Ticket 09 — OK após correção

Os dois achados de Standards acima também eram lacunas de Spec (AC03 e "execução
interrompida é reconciliável sem bloqueio permanente"); corrigidos antes deste registro,
não há requisito ausente/parcial, scope creep ou implementado incorretamente pendente.

### Ticket 10 — OK

Os dois achados de Standards acima também eram lacunas de Spec (AC08 — leitura
incompleta jamais pode escapar como algo diferente de `SincronizacaoIncompleta`);
corrigidos antes deste registro. O wiring de produção e a conservação de fato do
snapshot anterior, que dependiam do ticket 11, já estão fechados; a renderização
rica segue explicitamente destinada ao ticket 12.

### Ticket 11 — OK após correção

Os quatro achados de Standards acima também eram lacunas de Spec: o primeiro é
AC03 (reserva órfã que trava o ciclo); o segundo e o terceiro são AC09 (cache
precisa ficar visível e íntegro); o quarto quebraria a entrega de frases sem
relação com o problema real (uma frase sem rich text). Todos corrigidos antes
deste registro. Fora do escopo desta sessão, e não reclassificado como falha: a
renderização rica e a divisão inteligente de mensagens, explicitamente
destinadas ao ticket 12.

## Débitos deliberadamente encaminhados

Não contam como falha oculta do ticket que os originou:

- identidade completa e máquina de estados: ticket 07;
- intenção por parte, entrega incerta e retomada após confirmação: ticket 08;
- lease, token de versão e concorrência entre workers: ticket 09;
- retentativas, classificação de erro transitório e retomada automática: ticket 14.

O débito de concorrência do ticket 06 foi resolvido pelo ticket 09 (versão do ciclo e
lease do pedido). Do mesmo modo, o exercício AWS de 06 mostrou um pedido que precisou de
retomada manual; o ticket 14 já registra a necessidade de o reconciliador alcançar esse
estado. A substituição da fixture, prevista para os tickets 10 e 11, foi concluída em
ambos: a leitura/conversão no 10, a persistência/cache/wiring no 11.

## Resultado

- Tickets com code-review histórico declarado: **02, 05 e 06**.
- Tickets concluídos sem evidência histórica localizada de code-review: **03 e 04**.
- Ticket administrativo sem implementação de código a certificar: **01**.
- Tickets concluídos com review executado no diretório de trabalho: **07, 08, 09, 10 e
  11** — 09, 10 e 11 com achados corrigidos antes do commit.
- Tickets ainda pendentes: **12–22**.

Não há base para registrar “OK final pós-correção” em 02, 05 ou 06. O próximo marco
confiável é corrigir ou aceitar explicitamente os achados vigentes e executar novo
code-review sobre um ponto fixo posterior às últimas alterações.
