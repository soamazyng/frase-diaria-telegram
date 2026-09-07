# 09 — Lease, escritas condicionais e concorrência

**What to build:** dois workers rodando ao mesmo tempo deixam de ser um problema. Reserva de pedido e de frase passam a usar escrita condicional, e o estado do ciclo fica protegido por lease com prazo e token de versão, de modo que um executor antigo não consegue confirmar nem avançar uma reserva que já foi transferida para outro.

**Blocked by:** 08 — Intenção por parte, retomada e entrega incerta.

**Status:** ready-for-agent

- [ ] Reserva de pedido e de frase acontece por escrita condicional ou transação; não há janela em que dois executores reservem a mesma frase.
- [ ] O estado do ciclo e a sequência de envio são protegidos por lease de duração limitada com token de versão.
- [ ] Um executor cujo lease expirou não consegue confirmar entrega nem avançar o ciclo (AC03).
- [ ] Uma execução interrompida é reconciliável sem deixar bloqueio permanente.
- [ ] Lease expirado é registrado na observabilidade.
- [ ] Testes de concorrência do repositório exercitam atomicidade, retomada e corrida entre dois executores.
