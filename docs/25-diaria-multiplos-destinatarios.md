# Diária com múltiplos destinatários: entrega compartilhada e falhas independentes

## Comportamento

O pedido diário passa a carregar todos os destinatários autorizados (`telegram-chat-ids`)
num único pedido, identificado só pelo dia local (`diaria#<dia>`, sem chat_id). Uma única
frase é sorteada, reservada e consumida no ciclo — independentemente de quantos
destinatários existirem. O worker entrega a mesma frase a cada destinatário de forma
isolada: um erro permanente do Telegram para um destinatário (bot bloqueado, credencial
recusada) não impede, atrasa nem interrompe a entrega aos demais, e o pedido só é
considerado concluído quando todos tiverem recebido tudo.

`/frase` (extra) não muda: continua com identidade por `bot + update_id` e exatamente um
destinatário — quem pediu.

## Decisão técnica

**Todos os destinatários são tentados antes de decidir o desfecho do pedido.** O worker
(`ProcessarPedido._entregar`) itera cada destinatário através de um novo método,
`_entregar_a_destinatario`, que devolve um desfecho isolado (concluído / incerto / falhou
/ aguardando / janela esgotada) sem tocar o estado do pedido. Só depois de tentar todos —
exceto quando a janela se esgota, que interrompe a passada imediatamente — `_entregar`
decide o estado agregado, na prioridade janela > aguardando > incerto > falhou > concluído.
Essa prioridade decide **o que o pedido faz a seguir** (retentar ou encerrar), não o que
fica registrado como motivo — ver a correção do `/code-review` abaixo.

**Uma única reserva/consumo de frase, nunca por destinatário.** `Ciclo.consumir` só aceita
consumir uma frase reservada uma vez; tentar reservar/consumir por destinatário colidiria
com essa invariante (investigado antes da spec v2 — ver `.scratch/v2-telegram-bot.md`). A
reserva e o consumo continuam acontecendo no nível do pedido, como antes; o que muda é só
que um pedido agora pode ter mais de um destinatário para a mesma reserva.

**Rastreio de partes por destinatário.** A chave da parte no DynamoDB passou de
`parte#<indice>` para `parte#<destinatario>#<indice>` — a mesma parte pode ter desfechos
diferentes por destinatário (confirmada para um, incerta para outro). `Pedido.identidade_de_parte`
ganhou o parâmetro `destinatario` para refletir essa nova identidade.

**Compatibilidade com pedidos antigos.** Um pedido gravado antes da v2 (com `chat_id`
escalar, sem `destinatarios`) é lido como `destinatarios = (chat_id,)` — mesmo padrão já
usado para `bot_legado`/`estado_legado`. Partes antigas (`parte#<indice>`, sem
destinatário) não são migradas: um pedido pré-v2 ainda em andamento no exato momento do
deploy não seria retomado corretamente. O risco é pequeno (janela de 08:00–12:00, deploy
deliberado) e fica documentado aqui em vez de resolvido com uma migração de dado que este
ticket não pedia.

**Migração completa do parâmetro SSM.** Diferente do que o ticket 24 previa, este ticket
migrou tanto a diária quanto o webhook para `telegram-chat-ids` — `telegram-chat-id`
(singular) não é mais lido por nenhum código a partir desta entrega. Ele continua existindo
no SSM até o ticket 27 confirmar a migração em produção.

## Skills aplicadas

`/implement` e `/python-clean-code` seguidos. `/tdd` aplicado na fronteira de `_entregar`/
`_entregar_a_destinatario`: os testes do caminho feliz e da invariante de propósito foram
escritos e verificados antes de eu considerar a implementação pronta. `/code-review`
executado nos eixos Standards e Spec — cinco achados, todos corrigidos nesta mesma entrega
(ver "Review" abaixo).

## Testes

- `tests/dominio/test_pedido.py`: `Pedido.destinatarios` aceita múltiplos valores, rejeita
  conjunto vazio; nova identidade da diária e da parte.
- `tests/aplicacao/test_processar_pedido.py`: caminho feliz com dois destinatários (mesma
  frase, um único consumo no ciclo — AC32/AC34); falha permanente a um destinatário não
  afeta o outro, consumo com ressalva uma única vez (AC33); erro transitório a um
  destinatário reagenda o pedido inteiro; motivo agregado menciona todos os destinatários
  com problema; reagendamento usa o instante mais tardio entre os que aguardam. Toda a
  suíte pré-existente de destinatário único (extras) continua verde sem alteração de
  comportamento.
- `tests/persistencia/test_repositorio_de_pedidos.py`: múltiplos destinatários sobrevivem a
  gravar e recuperar; partes de destinatários distintos no mesmo pedido não se misturam;
  pedido legado sem `destinatarios` é lido com o `chat_id` antigo.
- `tests/aplicacao/test_consultar_status.py`: ajuste mínimo de compilação (`indices_incertos`
  por destinatário) mais um teste de transição (diária de ontem no formato anterior à v2
  ainda é encontrada).
- `make verificar`: 402 testes, ruff e mypy limpos.

## Review

`/code-review` (Standards e Spec) encontrou cinco achados, todos corrigidos nesta entrega:

1. **Motivo de um destinatário desaparecia quando outro tinha prioridade maior.** Um
   destinatário que falhou permanentemente perdia o próprio motivo registrado se, no mesmo
   instante, outro ficasse incerto (prioridade maior) — corrigido: o motivo agregado agora
   junta todos os destinatários com problema, não só o que decidiu o desfecho.
2. **Reagendamento usava só o primeiro destinatário em espera.** Com dois destinatários
   aguardando por motivos diferentes (um com `retry_after` curto, outro longo), a próxima
   tentativa usava o primeiro do tuple — corrigido: usa o instante mais tardio entre todos,
   para não bater cedo demais no limite de ninguém.
3. **Consultas duplicadas ao repositório.** `_algum_destinatario_confirmou` reconsultava
   `indices_confirmados` por destinatário mesmo quando `_entregar_a_destinatario` já tinha
   acabado de fazer a mesma consulta — corrigido: o resultado por destinatário agora carrega
   `confirmou_algo`, calculado uma única vez.
4. Comentário desatualizado em `reconciliar_pendencias.py` ainda descrevia a identidade da
   diária como "conversa + dia local" — corrigido.
5. **`/status` não encontraria a diária de ontem no dia da publicação da v2**, porque ela
   ainda estaria gravada no formato anterior (`diaria#<chat_id>#<dia>`) — corrigido com um
   fallback transitório em `consultar_status.py`, documentado para revisão futura.

## Próximo passo

Ticket 26 — `/status` reporta a entrega do próprio destinatário, substituindo o estado
agregado do pedido pela situação real de quem perguntou.