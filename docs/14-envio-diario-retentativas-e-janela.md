# Envio diário, retentativas e janela até 12:00

## Comportamento

Duas novas Lambdas, agendadas via EventBridge Scheduler, fecham o ciclo de
envio automático:

- **`AgendadorDiario`** dispara às 08:00 America/Sao_Paulo (o Scheduler resolve
  o fuso, sem conversão manual para UTC), materializa o pedido diário
  (`CriarDiaria`, já existente desde o ticket 07, agora conectado) e acorda o
  worker.
- **`Reconciliador`** roda a cada cinco minutos: alcança pedidos vencidos de
  **qualquer origem** — diária ou `/frase`, inclusive um pedido preso em
  `AGUARDANDO_TENTATIVA` por contenção de ciclo, achado observado na AWS no
  ticket 06 — e, dentro da janela 08:00–12:00 local, materializa a diária
  ausente se o disparo principal falhou.

O worker passou a distinguir erro transitório de erro permanente do Telegram
(AC13): 429 e 5xx agendam nova tentativa com espera progressiva (dobra a cada
tentativa, teto de 15 minutos, dispersão de até 10%, e respeito literal ao
`retry_after` quando o Telegram o informa); 401, 403 e demais 4xx encerram o
pedido com diagnóstico, sem repetição infinita. A checagem do prazo acontece
imediatamente antes de cada chamada ao Telegram — não uma vez por execução —
porque uma frase de várias partes pode atravessar o prazo no meio do envio.
Ao meio-dia local, uma diária pendente é encerrada com o que já foi
confirmado preservado: nada enviado vira `EXPIRADO` (libera a reserva), algo
já confirmado vira `PARCIAL` (consumo com ressalva, como qualquer entrega
incompleta).

Extras seguem a política já decidida pela usuária: criados antes do meio-dia
local, retentam até lá; criados a partir do meio-dia, têm uma tentativa
imediata e, falhando — transitória ou não —, encerram sem fila para o dia
seguinte.

## Decisão técnica

**Duas Lambdas novas, não uma reaproveitando o worker.** Cada função só tem a
permissão que usa: `AgendadorDiario` só grava o pedido diário (`PutItem`
condicional); `Reconciliador` só consulta o índice de pendências e cria a
diária ausente; nenhuma das duas transaciona pedido/ciclo/partes — isso
continua exclusivo do worker, que elas apenas acordam por invocação
assíncrona (`lambda:InvokeFunction`, restrito ao ARN do worker).

**`EventBridge Scheduler` (`ScheduleV2`), não `EventBridge Rules`** — é o que a
stack aprovada já previa, e é o único que aceita `ScheduleExpressionTimezone`
diretamente, dispensando conversão manual de fuso (inclusive se o offset de
`America/Sao_Paulo` um dia mudar).

**`Pedido.prazo: datetime | None`** é o prazo genuíno de abandono (meio-dia
local, para diária e extra criado de manhã). Ele não serve para "extra criado
a partir do meio-dia": o despacho do worker é sempre um pouco posterior à
criação do pedido, então um prazo baseado no próprio instante de criação
seria sempre visto como "já vencido" na primeira checagem, e a tentativa
imediata que a política promete nunca aconteceria. Por isso existe um segundo
campo, **`Pedido.tentativa_unica: bool`**: um extra tardio nasce com
`prazo=None` (nenhum abandono por tempo) e `tentativa_unica=True` (nenhuma
retentativa, mesmo diante de erro transitório) — os dois mecanismos resolvem
problemas diferentes e não se substituem. `dominio/tempo.politica_do_extra`
decide os dois de uma vez, na criação, a partir do instante local.

**Backoff usa o `sequencial` da tentativa** (já monotônico, de
`registrar_tentativa`) como expoente, em vez de manter uma contagem separada.
Ele conta toda tentativa do pedido, não só as que erraram por um erro
transitório do Telegram — uma retentativa por contenção de ciclo antes do
primeiro erro já infla o expoente. Aceito de propósito: o teto do backoff
limita o efeito, e separar as duas contagens exigiria persistir mais um
campo só para isto.

## Verificação

- Skills aplicadas: `implement`, `python-clean-code`, `tdd` e `code-review`.
- `ruff check`, `ruff format --check` e `mypy --strict`: OK.
- `sam validate --lint` nos dois templates (`infra/dados.yaml` sem mudança;
  `infra/aplicacao.yaml` com as duas funções novas): OK. Nenhuma publicação
  real foi feita nesta sessão.
- `pytest`: 328 testes passaram (dominío, aplicação, persistência, telegram e
  contrato), incluindo os novos: prazo/tentativa única em `dominio/tempo` e
  `dominio/pedido`; classificação transitório/permanente e extração de
  `retry_after` em `telegram/canal`; `CriarDiaria` e `ReconciliarPendencias`
  isolados; a checagem de prazo por parte (não por execução) e a tentativa
  imediata do extra tardio em `processar_pedido`; round-trip de `prazo` e
  `tentativa_unica` no repositório DynamoDB (`moto`); registro de atraso
  acima de 15 minutos (e ausência dele dentro do limite), por `caplog`.

## Review

Revisão em dois eixos (`/code-review`, agentes paralelos) sobre o diff antes
do commit.

**Standards** — um achado forte corrigido: a checagem de prazo rodava uma vez
por execução, não antes de cada chamada ao Telegram como o próprio `CLAUDE.md`
exige; movida para dentro do laço de envio. Três achados de julgamento
corrigidos: a ação `lambda:InvokeFunction`, repetida em três funções do SAM
sem âncora YAML, ganhou uma (`&acordarWorker`); a extração de `retry_after` em
`telegram/canal.py` estava duplicada entre dois pontos, unificada num só
helper; a constante do início da janela (08:00) vivia na camada de aplicação
enquanto o fim (12:00) vivia no domínio — as duas passaram a viver juntas em
`dominio/tempo`. Um achado de julgamento registrado e aceito sem mudança: o
backoff usa o `sequencial` de qualquer tentativa, não só as de erro
transitório do Telegram (ver "Decisão técnica" acima).

**Spec** — um achado forte, corrigido: a implementação original de
`prazo_do_extra` fazia um extra criado a partir do meio-dia nunca chegar a
chamar o Telegram (zero tentativas, não a uma tentativa imediata que a
política promete), porque o despacho é sempre posterior à criação. Resolvido
com a separação `prazo`/`tentativa_unica` descrita acima, com teste de
regressão. Um item do checklist estava ausente na primeira versão revisada —
o registro de atrasos acima de 15 minutos na observabilidade — e foi
implementado após o achado, com teste próprio. Os demais itens do ticket —
inclusive os dois achados citados no próprio arquivo da issue (classificação
de erro transitório do ticket 05; reconciliador alcançando pedidos além da
diária, do ticket 06) — foram confirmados cobertos.

## Próximo passo

O próximo ticket elegível é o **15 — /status completo** (depende dos tickets
11 e 14, ambos concluídos). A publicação real na AWS deste ticket — exercitar
o disparo agendado, o reconciliador e a janela contra o Telegram de verdade —
fica para quando a usuária autorizar uma nova publicação; nada foi publicado
nesta sessão.
