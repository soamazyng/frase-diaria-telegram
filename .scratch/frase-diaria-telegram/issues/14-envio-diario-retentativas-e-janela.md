# 14 — Envio diário, retentativas e janela até 12:00

**What to build:** a rotina finalmente existe: a frase chega sozinha às 08:00 no fuso de São Paulo, todos os dias, inclusive fins de semana, com o computador desligado. Falhas temporárias são retentadas até o meio-dia local; ao meio-dia a diária pendente é encerrada e não reaparece no dia seguinte.

**Blocked by:** 09 — Lease, escritas condicionais e concorrência.

**Status:** concluído em 2026-09-08 — ver `docs/14-envio-diario-retentativas-e-janela.md`

- [x] Um disparo agendado cria o pedido diário; relógio local entre 08:00 e 08:15 em dia normal produz uma diária, e fins de semana seguem a mesma regra (AC01).
- [x] Um segundo disparo periódico recupera pedidos pendentes e execuções interrompidas, e pode criar a diária ausente dentro da janela quando o disparo principal falhar.
- [x] A chave diária torna as duas entradas idempotentes: nunca resultam em duas diárias no mesmo dia local.
- [x] Instantes são gravados em UTC e a chave diária é calculada pelo dia local.
- [x] O próximo instante de tentativa é persistido; nenhuma execução fica dormindo esperando.
- [x] Espera progressiva limitada, com dispersão, respeitando o intervalo informado pelo Telegram quando houver.
- [x] A janela é conferida imediatamente antes de cada chamada ao Telegram.
- [x] Às 12:00 nenhuma nova chamada da diária é iniciada; a diária pendente, inclusive parcial, é encerrada com o resultado conservado, e não reaparece no dia seguinte (AC14).
- [x] Erro transitório agenda nova tentativa do mesmo pedido; erro permanente, como credencial inválida ou bot bloqueado, encerra com diagnóstico sem repetição infinita (AC13).
- [x] `/frase` usa o mesmo ciclo da diária e não a satisfaz nem a cancela (AC06).
- [x] Extra criado antes das 12:00 pode retentar até as 12:00; extra criado a partir das 12:00 tem uma única tentativa imediata e, falhando, encerra com diagnóstico, sem fila para o dia seguinte. *(Política decidida pela usuária: extras não entram em fila para o dia seguinte.)*
- [x] Atrasos acima de 15 minutos são registrados na observabilidade.

## Vindo do code-review do ticket 05

Hoje **qualquer** `ErroDoTelegram` — inclusive 429 e 5xx, que são transitórios —
leva o pedido a `FALHOU` ou `PARCIAL`, ambos terminais. Um único 429 momentâneo
encerra o pedido em definitivo, e tanto a retentativa da Lambda quanto o
reconciliador saem pelo `if pedido.estado.terminal`. O AC13 exige distinguir
transitório de permanente: o primeiro agenda nova tentativa do mesmo pedido, o
segundo encerra com diagnóstico.

**Resolvido:** `telegram/canal.py` classifica 429/500/502/503/504 como
transitórios (e extrai `retry_after` quando informado); os demais códigos são
permanentes. `processar_pedido.py` agenda retentativa com espera progressiva
para os transitórios, dentro do prazo do pedido.

## Observado no ticket 06, na AWS

Um `/frase` enviado em rajada caiu em `AGUARDANDO_RESERVA` — a última frase livre
estava reservada pelo pedido anterior. O pedido ficou corretamente fora de estado
terminal, mas **nenhum mecanismo o retomou**: as retentativas da invocação
assíncrona se esgotaram antes de o ciclo virar, e ele só foi entregue por
invocação manual.

O reconciliador periódico deste ticket precisa alcançar pedidos nesse estado, não
apenas os da diária.

**Resolvido:** `ReconciliarPendencias` varre `buscar_vencidos`, que não filtra
por origem nem por motivo de pendência — qualquer pedido não-terminal com
`processar_em` vencido é alcançado, inclusive um preso em
`AGUARDANDO_TENTATIVA` por contenção de ciclo.
