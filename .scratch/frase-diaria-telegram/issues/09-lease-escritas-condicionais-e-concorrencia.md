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

## Vindo do code-review do ticket 05

`RepositorioDePedidosDynamo.salvar` já usa `attribute_exists(pk)`, o que impede
inventar um pedido inexistente, mas **não** tem token de versão. Dois workers
concorrentes podem ler o mesmo pedido em `PENDENTE`, sortear frases diferentes,
ambos gravar e ambos enviar — frase duplicada e duas frases consumidas do ciclo.
A invocação assíncrona da Lambda pode entregar o mesmo evento mais de uma vez,
então o cenário não depende do reconciliador para acontecer.

## Vindo do code-review do ticket 06

`RepositorioDeCiclosDynamo.salvar` grava o item inteiro com `put_item`
incondicional. Dois workers que carregarem o mesmo ciclo, sortearem frases
diferentes e gravarem em sequência perdem a reserva de um dos dois — e as duas
frases podem sair no mesmo ciclo.

A reserva já é transacional (`persistencia/reserva.py`: ciclo e pedido mudam
juntos), o que elimina a reserva órfã, mas **não** protege contra sobrescrita.
Falta o token de versão no item do ciclo, com escrita condicional sobre ele.

Paliativo em vigor: `ProcessarPedido._consumir_no_ciclo` detecta que o ciclo
perdeu a reserva de uma frase já entregue, registra o desvio e consome mesmo
assim, em vez de deixá-la elegível de novo.
