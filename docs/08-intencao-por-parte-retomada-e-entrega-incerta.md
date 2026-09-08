# Intenção por parte, retomada e entrega incerta

**Ticket:** 08 — Intenção por parte, retomada e entrega incerta

## Objetivo

Garantir que uma execução interrompida não perca o histórico de partes já tentadas e que o worker não reenvie informações que podem já ter chegado ao Telegram. A política é conservadora: o sistema trata o resultado ambíguo como incerto e suspende reenvio automático dessa parte.

## Rastro antes do envio

Antes de chamar o Telegram, o worker registra a intenção de enviar uma parte. Isso cria um estado intermediário para a parte:

- `intencao`

A intenção não é confirmação. Ela só garante que a execução tenha um rastro durável antes do envio externo.

## Confirmação e risco ambíguo

Quando a Bot API confirma um `message_id` válido, a parte é marcada como `confirmada` com texto e identificador persistidos.

Quando a Bot API devolve `ok: true` sem `message_id`, o valor é tratado como ambíguo, e o sistema não classifica a parte como entregue. Em vez disso:

- grava o estado `incerto` para a parte
- salva a razão do risco
- encerra o pedido com `incerto`
- suspende reenvio automático dessa parte

O valor `0` é reservado para esse caso de ambiguidade, conforme a constante `MESSAGE_ID_DESCONHECIDO` do canal do Telegram.

## Retomada

Na retomada, o worker:

- ignora partes já confirmadas
- ignora partes marcadas como `incerto`
- não reenvia partes cuja intenção foi registrada sem confirmação durável
- retoma apenas as partes que faltam de fato

Em outras palavras, a retomada não reenvia o que já pode ter ocorrido; ela só continua o que ainda está comprovadamente pendente.

## Onde a política fica

A implementação está em:

- `src/frase_diaria/aplicacao/processar_pedido.py`
- `src/frase_diaria/persistencia/pedidos.py`
- `src/frase_diaria/telegram/canal.py`

A lógica central é:

1. registrar intenção antes do envio
2. enviar texto
3. confirmar somente quando houver `message_id` real
4. tratar ausência de identificador como estado incerto
5. reabrir/retomar somente partes pendentes e não ambiguamente entregues

## Estado do pedido

Quando a entrega entra em ambiguidade, o pedido é marcado em `incerto` e no ciclo a frase é consumida com ressalva, conforme a política estabelecida no projeto.

Esse comportamento reduz duplicação, aceitando explicitamente o risco de uma mensagem perdida em falha externa ambígua — política decidida pela usuária e documentada pela spec.

## Verificação

O gate do repositório foi executado e passou:

- `ruff`
- `mypy`
- `pytest`

Resultado local: 199 testes passaram.
