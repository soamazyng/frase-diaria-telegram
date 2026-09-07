# 14 — Envio diário, retentativas e janela até 12:00

**What to build:** a rotina finalmente existe: a frase chega sozinha às 08:00 no fuso de São Paulo, todos os dias, inclusive fins de semana, com o computador desligado. Falhas temporárias são retentadas até o meio-dia local; ao meio-dia a diária pendente é encerrada e não reaparece no dia seguinte.

**Blocked by:** 09 — Lease, escritas condicionais e concorrência.

**Status:** ready-for-agent

- [ ] Um disparo agendado cria o pedido diário; relógio local entre 08:00 e 08:15 em dia normal produz uma diária, e fins de semana seguem a mesma regra (AC01).
- [ ] Um segundo disparo periódico recupera pedidos pendentes e execuções interrompidas, e pode criar a diária ausente dentro da janela quando o disparo principal falhar.
- [ ] A chave diária torna as duas entradas idempotentes: nunca resultam em duas diárias no mesmo dia local.
- [ ] Instantes são gravados em UTC e a chave diária é calculada pelo dia local.
- [ ] O próximo instante de tentativa é persistido; nenhuma execução fica dormindo esperando.
- [ ] Espera progressiva limitada, com dispersão, respeitando o intervalo informado pelo Telegram quando houver.
- [ ] A janela é conferida imediatamente antes de cada chamada ao Telegram.
- [ ] Às 12:00 nenhuma nova chamada da diária é iniciada; a diária pendente, inclusive parcial, é encerrada com o resultado conservado, e não reaparece no dia seguinte (AC14).
- [ ] Erro transitório agenda nova tentativa do mesmo pedido; erro permanente, como credencial inválida ou bot bloqueado, encerra com diagnóstico sem repetição infinita (AC13).
- [ ] `/frase` usa o mesmo ciclo da diária e não a satisfaz nem a cancela (AC06).
- [ ] Extra criado antes das 12:00 pode retentar até as 12:00; extra criado a partir das 12:00 tem uma única tentativa imediata e, falhando, encerra com diagnóstico, sem fila para o dia seguinte. *(Política decidida pela usuária: extras não entram em fila para o dia seguinte.)*
- [ ] Atrasos acima de 15 minutos são registrados na observabilidade.
