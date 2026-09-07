# Lease, escritas condicionais e concorrência

**Ticket:** 09 — Lease, escritas condicionais e concorrência

## Objetivo

Fazer de dois workers rodando ao mesmo tempo um não-problema: a reserva de pedido e de frase passa a usar escrita condicional e transação, e o ciclo e a sequência de envio de cada pedido ganham proteção própria contra sobrescrita — um token de versão para o ciclo, um lease com prazo e token de versão para o pedido.

## Duas concorrências independentes

O ciclo é compartilhado por diárias e extras; o lease é próprio de cada pedido. São dois mecanismos distintos, resolvendo dois problemas distintos:

**Versão do ciclo** (`RepositorioDeCiclosDynamo`) — `carregar()` devolve o ciclo junto com a versão lida; `salvar(ciclo, versao_anterior)` só grava se essa versão ainda for a vigente, senão recusa com `ConflitoDeConcorrencia`. Impede que dois workers que leram o mesmo ciclo — para reservar frases diferentes, ou para concluir pedidos diferentes — sobrescrevam a gravação um do outro.

**Lease do pedido** (`RepositorioDePedidosDynamo`) — o sequencial de tentativa, já atômico e monotônico (`registrar_tentativa`), dobra como token do lease. `assumir_lease` reivindica a exclusividade sobre o envio deste pedido por tempo limitado (`DURACAO_DO_LEASE`, 5 minutos): um sequencial mais novo sempre pode assumir; um mais antigo só consegue depois que o lease vigente expirou. `salvar` e `confirmar_parte` aceitam o sequencial e recusam a escrita se ele já não for o dono do lease vigente — é o que impede um executor superado (por exemplo, o mesmo evento entregue duas vezes pela invocação assíncrona da Lambda) de confirmar entrega ou avançar o estado do pedido depois de perder a corrida (AC03).

## Onde a transação entra

`ReservaTransacional.efetivar` grava o ciclo e o pedido no mesmo `transact_write_items`: a condição de versão no ciclo e a condição de lease no pedido (mais a condição de estado já existente) fazem da mesma transação o ponto único onde dois executores concorrentes disputam a reserva. Só um dos dois confirma; o outro recebe `ConflitoDeConcorrencia` sem que nenhum dos dois itens tenha mudado.

## Reconciliável sem bloqueio permanente

- **Conflito ao reservar** (`reserva.efetivar`): o pedido não avançou nenhum estado ainda, então o worker registra `aguardar_tentativa` e propaga `ReservaPendente` — uma nova tentativa relê o ciclo e o pedido do zero.
- **Conflito ao consumir/liberar no ciclo** (depois que o pedido já está em estado terminal): não há mais como abortar o pedido, então `_retentar_no_ciclo` relê o ciclo vigente e tenta de novo, até `MAX_TENTATIVAS_DE_CICLO` (20) vezes. Regravar o ciclo não chama o Telegram nem repete nada visível à usuária, então o teto é generoso — existe só para não travar a Lambda para sempre se a condição nunca puder ser satisfeita. Esgotadas as tentativas, desiste e registra um erro — o próximo pedido que tocar a mesma frase reconcilia a divergência (o mesmo mecanismo de tolerância já existente desde o ticket 06).
- **Conflito de lease** (na aquisição, ou durante o envio): a execução foi superada por outra mais nova, não falhou. `executar` devolve o pedido como leu no início — nunca um estado parcial da tentativa abandonada — e registra o resultado `superado` na tentativa, visível para observabilidade e para o `/status`.

## Onde a política fica

- `src/frase_diaria/persistencia/ciclos.py` — versão do ciclo.
- `src/frase_diaria/persistencia/reserva.py` — transação com as duas condições.
- `src/frase_diaria/persistencia/pedidos.py` — lease do pedido (`assumir_lease`, `salvar` e `confirmar_parte` condicionados).
- `src/frase_diaria/aplicacao/processar_pedido.py` — orquestra a aquisição do lease, a retentativa do ciclo e o desfecho de cada tipo de conflito.
- `src/frase_diaria/aplicacao/portas.py` — `ConflitoDeConcorrencia`, comum aos dois mecanismos.

## Achado do code-review corrigido

O `/code-review` (eixos Standards e Spec) encontrou que, depois de `reserva.efetivar` persistir a versão seguinte do ciclo, a variável local `versao_ciclo` nunca avançava — então toda entrega que reserva e conclui na mesma execução (o caminho comum, sem concorrência nenhuma) caía num conflito de versão espúrio ao gravar o consumo, mascarado pela retentativa. Corrigido incrementando `versao_ciclo` logo após a reserva ser efetivada. O teste `test_reservar_e_entregar_na_mesma_execucao_nao_gera_conflito_de_versao` reproduz o defeito — falhava antes da correção (3 gravações em vez de 2) e passa depois — confirmado revertendo a correção e restaurando (`rules.md`: um guarda que nunca falhou não guarda nada).

O mesmo review apontou que `_retentar_no_ciclo` desistia em silêncio depois de poucas tentativas; a margem foi ampliada para 20, documentado na seção acima.

## Correção posterior ao commit (achada por um code-review de escopo mais amplo)

Uma revisão seguinte, rodada sobre o diff acumulado desde `main` (não só o diff do
ticket em andamento naquele momento), encontrou dois problemas neste ticket já
commitado:

- **Corrigido:** `assumir_lease` usava `lease_dono < :seq` (estrito). Um retry
  automático do SDK sobre a mesma tentativa — depois que a primeira chamada já
  tinha sucesso no servidor, mas a confirmação se perdeu num blip de rede —
  encontrava `lease_dono` já igual a `:seq`, não menor, e era recusado como se
  fosse de outro executor. Corrigido para `lease_dono <= :seq`, tornando a
  reivindicação idempotente para o próprio dono, como já era o caso em
  `salvar`, `confirmar_parte` e `ReservaTransacional.efetivar`. Regressão:
  `test_reassumir_o_proprio_lease_e_idempotente` (falha sem a correção,
  confirmado revertendo e restaurando).
- **Corrigido:** `_retentar_no_ciclo` relia sem nenhuma dispersão entre
  tentativas; sob contenção real, vários pedidos perdedores relêem e colidem
  juntos de novo. Adicionado um jitter pequeno (até 20 ms) entre retentativas.
- **Aceito e não corrigido:** a tradução de exceção do boto3
  (`ConditionalCheckFailedException`/`TransactionCanceledException`) para
  `ConflitoDeConcorrencia` se repete em cinco pontos (`pedidos.py` ×3,
  `ciclos.py`, `reserva.py`), com pequenas variações de exceção capturada e
  mensagem. É duplicação real, mas as cinco variantes divergem o suficiente
  (uma delas só traduz condicionalmente; outra precisa inspecionar
  `CancellationReasons`) para que uma abstração única valha o risco de
  introduzir uma nova assimetria, no orçamento desta sessão. Fica registrado
  como débito de limpeza, não de correção.

## Verificação

O gate do repositório foi executado e passou:

- `ruff check` e `ruff format --check`
- `mypy` estrito
- `pytest`

Resultado local: 214 testes passaram, incluindo testes de concorrência com dois executores disputando a mesma versão do ciclo, o mesmo lease de pedido, e a retomada após conflito — exercitados contra DynamoDB simulado (`moto`) para o repositório e com falsos em memória para a orquestração.
