# Como uma frase chega ao Telegram

**Ticket:** 05 — `/frase` entrega uma frase de fixture

## O caminho

```
Telegram  →  POST /telegram/webhook  →  frase-diaria-http
                                              │
                                    valida, registra o comando,
                                    cria o pedido, responde 200
                                              │
                                    invoca (assíncrono, "Event")
                                              ↓
                                        frase-diaria-worker
                                              │
                                    lê o pedido da PERSISTÊNCIA,
                                    reserva a frase, envia parte a
                                    parte, confirma cada uma
                                              ↓
                                          Telegram
```

**A fronteira HTTP nunca entrega a frase.** Ela registra o pedido e responde. A
entrega exigiria trabalho depois da resposta HTTP — que a spec descarta — e
esbarraria no limite curto de espera do Telegram.

**O worker lê o pedido da persistência, não do evento.** O despacho carrega só a
identidade (`{"pedido": "extra#42"}`). Assim um despacho atrasado nunca processa
um retrato velho do pedido, e qualquer disparo posterior — inclusive o
reconciliador do ticket 14 — consegue retomar de onde parou.

**Acordar o worker pode falhar sem prejuízo.** O pedido já está persistido; o
webhook responde 200 mesmo assim. Devolver erro faria o Telegram reentregar um
comando já registrado.

## Como o estado é guardado

Um pedido ocupa vários itens sob a mesma partição `pedido#<identidade>`:

| `sk` | Conteúdo |
|---|---|
| `pedido` | estado corrente, frase reservada, chat |
| `parte#000`, `parte#001`, … | uma parte entregue, com o **texto enviado** e o `message_id` |
| `tentativa#<instante>` | resultado de cada execução, com o erro sanitizado |

Partes e tentativas ficam **fora** do item do pedido porque o histórico não
expira: um item único cresceria até bater no teto de 400 KB do DynamoDB.

Cada parte guarda o **texto efetivamente enviado**, não uma referência à frase. É
o que preserva o histórico quando a origem muda depois — a frase pode ser editada
no Notion, e o que a usuária recebeu continua registrado como recebido.

## Regras de entrega

**Entrega confirmada exige as duas coisas:** o Telegram devolveu sucesso **e** a
confirmação foi persistida. Só o primeiro não basta — sem persistir, uma retomada
reenviaria a parte.

**A reserva vence o sorteio.** Uma nova tentativa reutiliza a frase já reservada.
Sortear outra deixaria a primeira consumida sem ter sido entregue.

**Falha sem nenhum envio libera a reserva**; falha depois de entregar alguma parte
mantém a frase consumida e o pedido em `parcial`, para não reiniciar
automaticamente algo que já pode ter chegado (spec, 4.4).

**A retomada envia apenas o que falta**, consultando os índices já confirmados.

## A coleção de exemplo

`infraestrutura/colecao_fixture.py` traz cinco frases embutidas, uma delas em duas
partes para exercitar a entrega lógica ocupando mais de uma mensagem. A autoria
vem **junto do texto**, literalmente, como estará no Notion: separá-la em campo
próprio exigiria heurística, e heurística inventa atribuição.

O ticket 10 troca essa classe pelo Notion. Os casos de uso não mudam — a fonte é
uma porta.

## Ainda não implementado

`/status` é reconhecido mas **não responde nada** — é o ticket 15. Enquanto isso,
mandar `/status` para o bot produz silêncio, não um erro.
