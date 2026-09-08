# Pedidos: identidades estáveis e máquina de estados

**Ticket:** 07 — Pedidos: identidades estáveis e estados persistidos

## Objetivo

Garantir que cada pedido tenha uma identidade estável, mantenha o histórico mesmo em reinícios e respeite uma máquina de estados rigorosa. Isso evita duplicação de envio, reabertura de pedidos concluídos e inconsistência no worker.

## Identidade do pedido

A identidade do pedido é persistente e não depende do texto da frase nem do instante da execução.

| Tipo | Identidade |
|---|---|
| Diária | `diaria#{chat_id}#{data_local}` |
| Extra | `extra#{bot}#{update_id}` |
| Parte | `#{pedido}#parte#{indice}` |
| Tentativa | `#{pedido}#tentativa#{sequencial}` |

A regra principal é: repetir o mesmo evento diário, repetir o webhook ou reprocessar a mesma tentativa não gera um novo pedido. O item persistido reconhece a identidade já conhecida.

## Conversão de tempo

Todos os instantes são gravados em UTC, mesmo quando a janela de envio é calculada no fuso local de São Paulo. A chave diária usa o dia local e não o instante em UTC, conforme a regra da janela e do agendamento.

## Estados persistidos

Os estados do pedido são:

- `pendente`
- `reservado`
- `enviando`
- `aguardando_tentativa`
- `enviado`
- `parcial`
- `incerto`
- `falhou`
- `expirado`

Estado terminal é qualquer um dos últimos cinco. Uma tentativa de alterar um estado terminal deve falhar; isso impede reabertura por evento duplicado.

## Transições permitidas

A regras de transição ficam em `frase_diaria.dominio.pedido`. O comportamento é intencional e não admite “avançar à força” por evento duplicado.

- `pendente -> reservado | aguardando_tentativa | falhou | expirado`
- `reservado -> enviando | aguardando_tentativa | falhou | expirado`
- `enviando -> aguardando_tentativa | enviado | parcial | incerto | falhou | expirado`
- `aguardando_tentativa -> reservado | enviando | aguardando_tentativa | falhou | expirado`

As transições inválidas levantam erro e não persistem.

## Motivo do estado

Cada transição registra um motivo textual, por exemplo:

- `pedido criado`
- `frase reservada`
- `envio iniciado`
- `todas as partes confirmadas`
- `entrega parcial`

Isso ajuda a diagnosticar o que aconteceu no `/status` e em logs sanitizados sem expor dados pessoais.

## Conteúdo extenso em itens separados

Para manter o item do pedido pequeno e evitar crescimento ilimitado, o histórico é separado:

- item principal do pedido: estado, reserva, metadata
- item por parte: texto efetivamente enviado e `message_id`
- item por tentativa: resultado, erro, instante, versão e correlação

Essa separação é o que permite consultar o histórico sem depender de um único payload gigante no DynamoDB.

## Índice de pendências

Pedidos pendentes são consultados pelo índice `pendencias`, usando:

- `pendencia = "pedidos"`
- `processar_em <= agora`

Isso permite buscar tarefas vencidas sem varrer o histórico inteiro da tabela. A migração do ticket também adota itens legados para esse índice, de forma idempotente.

## Regras de consistência

O que este ticket garante:

- uma vez gerado, um pedido mantém sua identidade
- reprocessamento de evento duplicado não cria outra execução
- estados terminais não reabrem por replay
- tentativa falha tem histórico preservado
- partes e tentativas ficam em itens separados para manter registro durável
- trabalho vencido pode ser encontrado por índice e processado em seguida

## Observações de implementação

A implementação fica em:

- `src/frase_diaria/dominio/pedido.py`
- `src/frase_diaria/persistencia/pedidos.py`
- `src/frase_diaria/persistencia/migrar_pendencias.py`

Os testes focados do ticket estão em:

- `tests/persistencia/test_repositorio_de_pedidos.py`

## Verificação

O gate do repositório foi executado e passou:

- `ruff`
- `mypy`
- `pytest`

Resultado local: 198 testes passaram.
