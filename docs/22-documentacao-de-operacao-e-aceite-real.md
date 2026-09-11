# Documentação de operação e aceite real controlado

## Escopo desta entrega

Ticket 22 tem dois tipos de item: documentação/verificação segura e ações
reais visíveis para a usuária. As primeiras foram feitas de imediato; as
segundas — `/frase` e `/status` na conversa privada — ficaram pendentes
até autorização específica, dada e exercitada em sessão seguinte (ver
"`/frase` e `/status` reais" abaixo). A entrega **diária** agendada (às
08:00) já está confirmada em uso normal pela usuária, independente desta
sessão. Só o item de avaliação pessoal após duas semanas de uso (AC31)
continua pendente — não pode ser satisfeito agora por definição, precisa
de duas semanas reais de uso passarem.

## `/frase` e `/status` reais, exercitados na conversa privada

Autorizado pela usuária e disparado de verdade contra a API pública do
webhook (`POST /telegram/webhook`, mesmo endpoint que o Telegram usa),
simulando exatamente o corpo que um `/frase` e um `/status` reais dessa
conversa produziriam — sem tocar segredos na saída visível: o token do
webhook e o `chat_id` foram lidos do SSM só para a chamada, nunca
impressos.

- **`/status`: entregue e confirmado.** Log do worker: `status enviado`
  (690 ms). A usuária confirmou o recebimento.
- **`/frase`: entregue, mas classificado internamente como incerto —
  achado real, não um bug de duplicação.** A tentativa 1 terminou em
  `erro` (exceção não classificada, ~20s de duração — mais abaixo). A
  tentativa 2 terminou em `incerto` (~16,5s) e o pedido ficou `parcial`,
  reenvio automático suspenso. A usuária confirmou ter recebido a frase
  **uma única vez** — ou seja, a tentativa 2 realmente entregou a
  mensagem no Telegram, mas a aplicação não conseguiu confirmar isso a
  tempo, e por desenho preferiu marcar como incerto a arriscar duplicar.
  **Isto é exatamente a limitação já documentada e aceita** ("sem garantia
  de entrega exatamente uma vez sob falha externa ambígua") acontecendo de
  verdade, com o resultado correto: nenhuma duplicata, mensagem entregue,
  reenvio automático corretamente suspenso.
- **Achado novo, não corrigido aqui — gap real de classificação,
  localizado com precisão pelo `/code-review`.** O traceback mostra uma
  exceção genérica (`except Exception` em
  `aplicacao/processar_pedido.py:190-194`) — não uma das exceções de
  domínio conhecidas (`ReservaPendente`, `ConflitoDeConcorrencia`) nem um
  resultado classificado como transitório pelo `telegram/canal.py`. A
  primeira hipótese registrada aqui ("timeout de rede sem resposta HTTP")
  estava tecnicamente errada — esse caso já é capturado por
  `except urllib.error.URLError` em `canal.py:81` e reclassificado como
  transitório antes de chegar ao catch-all. **O gap real é mais estreito:**
  `resposta.read()` (`canal.py:71`) roda *dentro* do mesmo `try` que
  captura `URLError`, mas um timeout ali levanta `socket.timeout`
  (`TimeoutError`), não `URLError` — ou seja, um timeout durante a
  *leitura* da resposta, depois que a conexão HTTP já foi estabelecida,
  escapa da classificação transitório/permanente do AC13 e cai direto no
  catch-all genérico, consistente com a duração de ~20s observada. Não
  corrigido aqui — exigiria mudança de código (capturar `TimeoutError`
  também) fora do escopo documental deste ticket — registrado como
  limitação remanescente, candidato a um ticket futuro se voltar a
  acontecer.

## Runbook de operação (AC30)

Este runbook não duplica os documentos por ticket — reúne, por tarefa, o
que já está espalhado e aponta a fonte exata.

### Configurar credenciais

Os quatro segredos do projeto ficam no SSM Parameter Store, prefixo
`/frase-diaria/`, como `SecureString` — nunca no Git, nunca colados numa
conversa com agente. Procedimento completo, incluindo o comando exato e a
recomendação de gerar valores diretamente para o cofre sem passar pela
conversa: `rules.md`, seção "Segredos".

- `telegram-bot-token`, `telegram-chat-id`, `webhook-secret`: ver
  `rules.md` e `CLAUDE.md` ("Segredos") para o que cada um guarda.
- `notion-token`, `notion-pagina-id`: mesmo mecanismo; aceita o id puro ou
  a URL completa da página (o cliente normaliza) — `CLAUDE.md`, "Segredos".
- **Rotação:** trocar o valor no SSM não basta sozinho — a Lambda cacheia
  segredos por container (`lru_cache` em
  `infraestrutura/composicao.py`); o efeito só é imediato depois de
  republicar (`rules.md`, "Publicar").

### Diagnosticar uma falha

- **Primeira parada: `/status`** (ticket 15) — último envio confirmado,
  próxima diária, situação do dia, origem da coleção (Notion ou cache),
  falha ativa — tudo em horário local, sem consumir frase nem alterar
  ciclo (`docs/15-status-completo.md`).
- **Publicação:** `GET /health` no endpoint publicado (`CLAUDE.md`) mostra
  versão ativa, dependências e agendamento. O passo "Verificar saúde,
  versão, dependências, webhook e agendamento" do pipeline
  (`.github/workflows/pr-develop-main.yml`,
  `.github/actions/diagnosticar-publicacao`) faz a mesma checagem
  automaticamente a cada publicação.
- **Logs:** CloudWatch Logs, retenção de 14 dias, conteúdo estruturado
  mínimo — nunca payload completo do Telegram/Notion nem segredos
  (`AGENTS.md`, "AWS Lambda e infraestrutura").
- **Issues abertas automaticamente:** um diagnóstico malsucedido que
  desabilita o agendamento diário sempre abre uma issue no GitHub com o
  procedimento manual específico daquele caminho — ver os passos
  "Registrar diagnóstico no GitHub" em `pr-develop-main.yml` e
  `reconciliador.yml`.

### Executar uma recuperação

- **Automática, dentro do próprio pipeline:** falha de deploy ou de
  diagnóstico pós-publicação já aciona recuperação para a última
  publicação saudável sem intervenção — `docs/19-recuperacao-da-versao-anterior.md`
  (dois testes de fogo reais documentados, incluindo o achado do
  `always()` faltando e a correção).
- **Periódica, sem ninguém para reagir:** implantação travada ou PR
  fechado sem merge são cobertos de hora em hora pelo reconciliador —
  `docs/20-reconciliador-de-publicacoes-e-dados.md`.
- **Procedimento manual de último recurso** (quando a recuperação
  automática também falha, ex. artefato com retenção expirada): `git
  checkout <sha-válido>` seguido de `make publicar-app VERSAO=<sha-válido>`
  a partir de um checkout local, publicando exatamente esse commit;
  reabilitar o agendamento diário depois é responsabilidade manual (AWS
  Console ou `aws scheduler update-schedule`) — mesmo texto que a issue
  automática já entrega quando esse caminho é necessário.
- **Limitação conhecida deste procedimento manual:** ele não passa pela
  API de Deployments do GitHub, então o reconciliador e a verificação
  pós-merge (ticket 21) continuam enxergando a última implantação
  registrada automaticamente até a próxima publicação normal — aceito,
  documentado, não é um caminho usado no dia a dia.

## Aceite na AWS

- [x] **`/frase` e `/status` exercitados na conversa privada** — feito, ver seção dedicada acima. Confirmado pela usuária: as duas mensagens chegaram, uma única vez cada.
- [x] **Entrega diária real (agendada, 08:00)** — confirmada pela usuária em uso normal, sem ação especial desta sessão: "diariamente eu já estou recebendo as mensagens, está tudo ok" (2026-09-11). Não é um teste isolado desta entrega, é a operação de regime já em curso.
- [x] **Persistência entre versões (AC26) — verificado ao vivo, read-only, no nível de metadado da tabela.** A tabela `frase-diaria-estado` (`aws dynamodb describe-table`) mostra `CreationDateTime: 2026-09-07T13:12:34-03:00` e 146 itens — sobreviveu, sem recriação, às dezenas de republicações da stack de aplicação feitas nos tickets 18–21 desde então. A stack `frase-diaria-dados` nunca foi atualizada desde a criação (`LastUpdatedTime` igual a `CreationTime`, a 6 segundos de diferença), confirmando que nenhuma dessas republicações da aplicação a tocou. **Ressalva:** isto confirma que nenhuma linha foi apagada nem a tabela recriada; não é uma leitura de conteúdo de um ciclo específico antes/depois de um deploy, então uma corrupção silenciosa de valores (sem mudar contagem de itens) não seria detectada por esta checagem.
- [x] **Achado real — drift entre template e recurso implantado, corrigido.** `infra/dados.yaml:26` declara `DeletionProtectionEnabled: true` (proteção nativa do DynamoDB, complementar ao `DeletionPolicy: Retain` do CloudFormation — o comentário do próprio template diz "sem os dois, um DeleteTable avulso apaga o histórico"). A tabela real estava com essa proteção **desligada** (`describe-table` → `DeletionProtectionEnabled: false`), porque a stack `frase-diaria-dados` nunca tinha sido reaplicada desde que essa linha entrou no template. **Corrigido ao vivo, autorizado pela usuária:** `make publicar-dados` rodou um changeset com uma única mudança (`Modify Tabela`), completou `UPDATE_COMPLETE`, e `describe-table` confirmou depois `DeletionProtectionEnabled: true` — com os mesmos 146 itens de antes, sem perda de dado. `DeletionPolicy: Retain` (o outro lado da proteção, contra exclusão da própria stack) segue ativo e não foi testado ao vivo nesta sessão.
- [x] **Nenhum ambiente permanente de dev criado.** `aws cloudformation list-stacks` mostra cinco stacks na conta. Três são deste projeto (`frase-diaria-bootstrap`, `frase-diaria-app`, `frase-diaria-dados`). Uma quarta, criada automaticamente pelo `--resolve-s3` do próprio `Makefile` deste projeto (bucket de staging de artefato do SAM CLI, sem função de "ambiente" — só empacotamento), tem data de criação de segundos antes da stack `frase-diaria-dados`, confirmando que também é deste projeto, não de outro material (checado ao vivo antes de afirmar — a suposição inicial de que seria alheia estava errada). A quinta, um ambiente Elastic Beanstalk, tem data de criação de 2023, quase três anos antes deste projeto começar — essa sim, de outro trabalho na mesma conta compartilhada. Nenhuma das cinco é um ambiente de *dev* da aplicação deste projeto.
- [x] **Recuperação exercitada de forma controlada** — já satisfeito por exercícios reais anteriores desta sessão, não repetido aqui: os dois testes de fogo do ticket 19 (falha de deploy e falha de diagnóstico, ambos revertidos) e a execução real do reconciliador contra o cenário de "candidata abandonada" no ticket 20 (falso positivo real, corrigido e reexercitado com sucesso). Ver `docs/19-recuperacao-da-versao-anterior.md` e `docs/20-reconciliador-de-publicacoes-e-dados.md`.

## Estimativa de custo (ticket 01) vs. consumo real observado

Consulta ao vivo em 2026-09-11, contra a conta e o repositório reais.

| Item | Estimado (ticket 01) | Real observado | Situação |
|---|---|---|---|
| GitHub Actions (minutos/mês) | ~880 de 3.000 (29%) | **154 min** em setembro (parcial, até dia 11), custo líquido **US$0** (desconto integral do plano Pro) | Dentro do esperado; folga ainda maior que a estimada |
| Lambda — invocações/mês | ~8.730 | 2.178 até agora no mês (Always Free: 1.000.000/mês) | 0,2% da franquia |
| Lambda — GB-segundos/mês | ~1.100 | 193,97 até agora (Always Free: 400.000/mês) | <0,1% da franquia |
| EventBridge Scheduler | ~8.670/mês | `frase-diaria-reconciliador` confirmado em `rate(5 minutes)` (Always Free: 14.000.000/mês) — volume real ainda baixo porque o agendamento roda há poucos dias desde o ticket 14, sem contagem real de invocações do mês inteiro observada ainda | Projeção consistente com a estimativa: 8.670/14.000.000 = 0,06% da franquia em regime pleno (mesmo cálculo de `docs/01-custo-e-elegibilidade.md`), não uma medição ao vivo |
| DynamoDB (armazenamento) | poucos MB, R$0 | 6,92×10⁻⁶ GB de 25 GB (Always Free) | Desprezível, como estimado |
| Custo real atribuído ao projeto (Cost Explorer, setembro) | ~US$0,01/mês (estimado) | Amazon API Gateway **US$0,0001** + Amazon DynamoDB **US$0,0012** = **US$0,0013** no mês até agora | Melhor que a estimativa |

**Conclusão:** a estimativa do ticket 01 se confirma na operação real — nenhum
serviço deste projeto sai do Always Free, e o custo direto atribuível (fora
GitHub Actions, coberto pelo plano Pro já existente) é uma fração de
centavo por mês. Outros itens de custo apareceram na mesma consulta ao
Cost Explorer (Lightsail, Route 53, VPC) — nenhum template deste projeto
declara esses serviços (`grep` confirmado em todos os `infra/*.yaml`,
consistente com a decisão registrada "sem VPC nem NAT"), o que torna
provável que sejam de outro material na mesma conta compartilhada
(`docs/01-custo-e-elegibilidade.md` já registra essa conta como
compartilhada com material de estudo). **Não confirmado por tag ou id de
recurso** — a mesma conta já teve, no ticket 01, um recurso criado por
engano durante uma sondagem deste próprio projeto, então a origem não deve
ser presumida sem essa checagem adicional caso vire relevante no futuro.

## Limitações remanescentes (registro explícito)

- **Sem garantia de entrega exatamente uma vez sob falha externa ambígua**
  (spec, seção sobre idempotência) — banco e chamada ao Telegram não estão
  na mesma transação; um resultado ambíguo marca a parte como incerta e
  **suspende reenvio automático** dessa parte, aceitando o risco de uma
  mensagem perdida em troca de nunca duplicar. Decisão confirmada da
  usuária (`CLAUDE.md`, "Decisões confirmadas"). **Exercitada de verdade
  nesta sessão** (seção "`/frase` e `/status` reais" acima): resultado
  correto na prática — entrega única, sem duplicata, reenvio suspenso.
- **Gap real na classificação de timeout durante a leitura da resposta do
  Telegram** — achado na mesma exercitação real, mecanismo localizado com
  precisão pelo `/code-review` (ver seção "`/frase` e `/status` reais"
  acima para o detalhe): `resposta.read()` em `canal.py:71` roda dentro do
  `try` que só captura `URLError`; um timeout ali levanta `TimeoutError`,
  que escapa dessa captura e cai no catch-all genérico de
  `processar_pedido.py:190`, sem ser classificado como transitório pelo
  AC13. Não corrigido — exigiria mudança de código (capturar
  `TimeoutError` também) fora do escopo documental deste ticket. Candidato
  a ticket futuro se se repetir.
- ~~Deletion protection do DynamoDB fora de sincronia com o template~~ —
  achado nesta entrega, corrigido ao vivo (ver seção "Aceite na AWS"
  acima).
- **Procedimento manual de recuperação de último recurso não atualiza a
  API de Deployments** — aceito, ver runbook acima.
- **Três cópias quase idênticas do loop "achar a última implantação
  bem-sucedida"** entre `pr-develop-main.yml`, `reconciliador.yml` e
  `verificar-merge.yml`, e três chamadas `gh issue create` sem
  deduplicação — trade-offs deliberados, registrados em `docs/20` e
  `docs/21`, para não arriscar regressão numa lógica já exercitada ao vivo
  extraindo uma composite action sem tempo de retestar com o mesmo rigor.
- **`iam:UpdateRoleDescription` ausente na identidade local** (`docs/20`)
  — qualquer mudança futura de `Description` de uma role em
  `infra/bootstrap.yaml` trava a stack em `UPDATE_ROLLBACK_FAILED`; o
  procedimento de destravamento já está documentado.
- **Avaliação pessoal de duas semanas (AC31)** — não pode ser satisfeita
  nesta sessão nem em nenhuma sessão futura antes do prazo; fica como
  pendência explícita, não como item esquecido.

## Review

Sem código Python nesta entrega — princípios gerais de clareza e não
duplicação de `python-clean-code` aplicados à prosa: cada seção do runbook
aponta para uma única fonte de verdade em vez de reexplicar, e os achados
reais (drift de `DeletionProtectionEnabled`) são descritos com o comando
exato que os revelou, não uma afirmação sem verificação.

`/code-review` (agente em background) encontrou 7 achados, todos
corrigidos:

- Dois checkboxes trocados na seção "Aceite na AWS": o item da entrega
  real (pendente) estava `[x]`, o da recuperação exercitada (já satisfeito)
  estava `[ ]` — invertidos entre si, contradizendo o próprio texto de
  cada linha.
- Percentual da franquia do EventBridge Scheduler citado como "0,9%"
  (na verdade o valor de outra linha da tabela, invocações do Lambda) em
  vez do "0,06%" correto, e apresentado como consumo já comprovado quando
  era projeção.
- **Achado mais sério:** a afirmação de que `aws-sam-cli-managed-default`
  era "de outro material" estava errada e não verificada — a stack tem
  data de criação de segundos antes de `frase-diaria-dados`, confirmando
  que é a própria stack de staging que o `--resolve-s3` deste projeto cria
  automaticamente. Corrigido depois de checar a data de criação ao vivo em
  vez de presumir pelo nome.
- Número da conta AWS reproduzido entre aspas ao citar `docs/01`, contra a
  regra do `AGENTS.md` de não repetir um identificador só porque ele já
  aparece em outro lugar do repositório — removido, mantida só a
  referência ao documento.
- Alegação de AC26 mais forte que a evidência (metadado de tabela, não
  conteúdo de um ciclo específico) — ressalva adicionada.
- Conclusão sobre Lightsail/Route53/VPC pertencerem a outro material
  suavizada para "provável, não confirmado por tag/id de recurso",
  citando o precedente do ticket 01 de um recurso criado por engano na
  mesma conta.

Uma segunda rodada de `/code-review`, sobre o registro do aceite real
(`/frase`/`/status`), encontrou mais 2 achados, ambos corrigidos:

- Citação de linha errada por off-by-one: o `except Exception` fica em
  `aplicacao/processar_pedido.py:190`, não `189-192`.
- **A hipótese técnica do "gap" estava errada** — um timeout de conexão
  puro (sem resposta HTTP nenhuma) já é capturado por
  `except urllib.error.URLError` em `canal.py` e reclassificado como
  transitório; nunca chegaria ao catch-all. O `/code-review` localizou o
  mecanismo real: `resposta.read()` roda dentro do mesmo `try` que só
  pega `URLError`, e um timeout *durante a leitura* da resposta (depois
  da conexão já estabelecida) levanta `TimeoutError`, que escapa dessa
  captura. Corrigido para descrever o mecanismo real, verificado lendo o
  código de `canal.py` linha a linha, não apenas aceitando a correção.

## Próximo passo

1. Registrar a avaliação pessoal depois de duas semanas de uso (AC31) —
   a diária já está confirmada em regime desde antes desta entrega, então
   a contagem das duas semanas corre a partir de quando a usuária começou
   a usar, não desta sessão.
2. Considerar investigar o gap de classificação de erro de rede (seção
   "Limitações remanescentes") se ele voltar a acontecer.

Com isto, todos os itens do ticket 22 sob controle desta sessão estão
concluídos; só resta o item de tempo (AC31).
