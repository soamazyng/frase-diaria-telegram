# Seleção sem repetição e ciclos

**Ticket:** 06 — Seleção sem repetição e ciclos persistidos

## O que é um ciclo

Um **ciclo** é o conjunto de frases consumidas desde o último reinício da
seleção. Ele guarda três coisas, e a diferença entre elas é o que faz o sorteio
funcionar:

| Conjunto | Significa | Sai das elegíveis? |
|---|---|---|
| **consumidas** | já entregues neste ciclo | sim, até o próximo ciclo |
| **reservadas** | presas a um pedido em andamento | sim, enquanto durar |
| **última entregue** | a mais recente | não; usada só na virada |

O ciclo **nunca guarda a lista de frases ativas** — ela vem da fonte a cada
consulta. É por isso que uma frase inserida entra no ciclo atual e uma excluída
some das elegíveis, sem que o ciclo precise saber que a coleção mudou (AC07).

## As duas regras que o ticket cobra

**AC04 — percorrer sem repetir.** A seleção sorteia apenas entre as frases ativas
que não estão consumidas nem reservadas. Com N frases estáveis, N entregas têm N
identidades distintas.

**AC05 — a virada não repete.** Quando o ciclo se esgota, o seguinte abre
excluindo a última frase entregue das candidatas à **primeira** seleção. Depois
dessa primeira entrega a regra deixa de valer, e a frase volta a concorrer como
qualquer outra.

Os três casos de borda:

| Frases ativas | Primeira do novo ciclo |
|---|---|
| zero | não há candidata; registra ausência de conteúdo |
| uma | repete — é inevitável e permitido |
| duas ou mais | qualquer uma, menos a última entregue |

## Quando o ciclo reinicia

Só quando **todas as ativas foram consumidas e não há reserva pendente**. A
segunda condição não é detalhe: reiniciar com um pedido em andamento poria a
mesma frase em dois ciclos ao mesmo tempo.

Se todas foram consumidas mas uma segue reservada, a seleção devolve "nada a
entregar" em vez de reiniciar. O pedido em andamento termina, libera ou consome a
reserva, e o ciclo vira na próxima seleção.

## Quando o consumo é marcado

**Só depois de entrega completa confirmada.** Antes disso a frase está apenas
reservada.

| Desfecho | Efeito no ciclo |
|---|---|
| Todas as partes confirmadas | consumida |
| Falha sem nenhum envio | **liberada** — volta às elegíveis |
| Entrega parcial | consumida **com ressalva** |

A ressalva é o que impede o bot de reenviar automaticamente algo que já pode ter
chegado: a frase conta como gasta, e a dúvida fica registrada no ciclo para o
`/status` (ticket 15) mostrar.

## Reserva no ciclo antes do pedido

A ordem importa: a frase é reservada **no ciclo** antes de o pedido guardar a
reserva. É o ciclo que impede outro pedido de sortear a mesma frase; gravar
primeiro no pedido deixaria uma janela em que a frase parece livre.

## Onde o estado mora

Um item, `pk = "ciclo"` e `sk = "atual"`, com o número do ciclo, os três
conjuntos e a última entregue. Cabe em um item porque o ciclo é limitado pela
coleção — algumas dezenas de identidades — e zera a cada reinício.

Não confundir com o histórico: o que foi de fato entregue vive nas partes e
tentativas de cada pedido, em itens próprios, e não é apagado quando o ciclo
reinicia.

> O DynamoDB recusa conjuntos vazios. Um ciclo recém-aberto tem três deles, e por
> isso a gravação omite o atributo em vez de gravar vazio.

## Quando não há frase, o motivo decide o destino

| Motivo | Definitivo? | Desfecho |
|---|---|---|
| `COLECAO_VAZIA` | sim | encerra o pedido, registrando ausência de conteúdo |
| `AGUARDANDO_RESERVA` | **não** | propaga para uma nova tentativa alcançar |

A distinção não é acadêmica: `AGUARDANDO_RESERVA` acontece quando todas as frases
foram consumidas e a última segue reservada por um pedido em andamento. Encerrar
ali levaria o pedido a estado terminal — e a diária das 08:00 morreria porque um
`/frase` estava em curso, sem que a janela até 12:00 pudesse reabri-la.

## Ainda não protegido

A gravação do ciclo sobrescreve o item inteiro, **sem token de versão**. Dois
workers concorrentes podem ler o mesmo ciclo, sortear frases diferentes e ambos
gravar: o último a escrever apaga a reserva do outro. A transação garante que
ciclo e pedido mudem juntos, mas não impede essa sobrescrita.

O paliativo está no consumo: quando o ciclo perdeu a reserva de uma frase já
entregue, o worker registra o desvio e consome mesmo assim, em vez de deixá-la
elegível de novo. A proteção de verdade — lease com prazo e token de versão — é
o **ticket 09**.

## Exercitado na AWS em 2026-09-07

Seis `/frase` em rajada, contra a coleção de cinco frases.

**Ciclo 1** entregou as cinco sem repetir: `fixture-03`, `04`, `05` (duas
partes), `01`, `02`. **Ciclo 2** abriu sozinho e começou por `fixture-03` — a
última do ciclo anterior era `fixture-02`, e a regra da virada foi respeitada.

**Um pedido caiu em `AGUARDANDO_RESERVA`.** Enviados em rajada, um deles rodou
quando a última frase livre estava reservada pelo pedido anterior, ainda em
entrega. O worker registrou a tentativa como `aguardando`, propagou
`ReservaPendente` e deixou o pedido **fora de estado terminal**.

Invocar o worker de novo nesse pedido, depois de o ciclo virar, entregou a frase
normalmente. É a prova de que a distinção entre `COLECAO_VAZIA` e
`AGUARDANDO_RESERVA` importa: encerrado como falha, o pedido teria batido no
`estado.terminal` e a retomada não faria nada.

O que falta é **quem** retoma sozinho. As retentativas da invocação assíncrona se
esgotaram antes de o ciclo virar, e o pedido ficou parado até a retomada manual.
Esse é o papel do reconciliador do ticket 14.
