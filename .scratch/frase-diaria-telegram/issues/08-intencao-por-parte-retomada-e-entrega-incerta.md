# 08 — Intenção por parte, retomada e entrega incerta

**What to build:** uma execução interrompida no meio de um envio pode ser retomada sem perder o que já aconteceu e sem reenviar o que já pode ter chegado. O bot registra a intenção de enviar cada parte **antes** de chamar o Telegram, de modo que uma queda entre a chamada e a confirmação deixa um rastro em vez de um buraco.

**Blocked by:** 07 — Pedidos: identidades estáveis e máquina de estados.

**Status:** ready-for-agent

- [ ] A intenção de envio é registrada por parte antes da chamada ao Telegram; a confirmação e o message_id são persistidos depois.
- [ ] Reinício após a reserva, após o envio e durante a confirmação não perde histórico; intenção sem confirmação resulta em estado incerto (AC15).
- [ ] Entrega parcial retoma somente as partes comprovadamente pendentes (AC16).
- [ ] Resultado ambíguo marca a parte como incerta e **suspende o reenvio automático** dessa parte; partes incertas nunca são reenviadas sozinhas (AC16).
- [ ] Sucesso externo conhecido com persistência temporariamente indisponível tenta persistir a confirmação sem reenviar.
- [ ] Pedidos incertos são registrados na observabilidade e ficam visíveis para o `/status`.
- [ ] O risco aceito está documentado no código ou no repositório: esta política troca a possibilidade de uma entrega perdida pela garantia de não duplicar.

> **Política decidida pela usuária:** tratamento conservador da entrega incerta — suspender o reenvio automático, aceitando explicitamente o risco de uma mensagem perdida em falha externa ambígua. A spec não promete entrega exatamente uma vez sob falha ambígua (seção 6).

## Vindo do code-review do ticket 05

Hoje `ProcessarPedido` envia a parte e **só depois** persiste a confirmação. Se
essa escrita falhar, ou o processo morrer entre as duas, a retomada reenvia a
mesma parte — mensagem duplicada para a usuária. É exatamente o que este ticket
resolve: registrar a intenção antes do envio e marcar *incerto* no resultado
ambíguo.

Ver também `MESSAGE_ID_DESCONHECIDO` em `telegram/canal.py`: quando a Bot API
responde `ok: true` sem identificador, hoje a parte conta como entregue com
identificador zero. Esse é um caso legítimo de **entrega incerta** e deveria
receber o tratamento deste ticket.
