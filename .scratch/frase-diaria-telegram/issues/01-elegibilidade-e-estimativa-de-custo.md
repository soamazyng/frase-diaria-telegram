# 01 — Elegibilidade e estimativa de custo AWS/GitHub

**What to build:** antes de qualquer provisionamento, saber se a meta de custo recorrente R$0 é alcançável e sob quais condições. Ao fim deste ticket existe um documento datado que diz em qual conta e região o projeto roda, quais franquias cobrem quais serviços, o que custa se a franquia acabar, e como consultar o consumo real depois.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Conta AWS, região e identidade para bootstrap confirmadas e registradas.
- [ ] Elegibilidade de franquias verificada item a item: API Gateway HTTP API, Lambda, DynamoDB e índices, S3 e requisições, EventBridge Scheduler, CloudWatch Logs, armazenamento de segredos e KMS, tráfego de saída.
- [ ] Custo da varredura periódica do reconciliador (proposta de 5 em 5 minutos) incluído na estimativa, com o número de invocações mensais explícito.
- [ ] Plano do GitHub verificado quanto a minutos de Actions, armazenamento de artefatos e permissão para Actions criarem PR.
- [ ] Documento registra que VPC/NAT não será usado, ou justifica a necessidade demonstrada.
- [ ] Documento registra a data da consulta e o procedimento para acompanhar consumo AWS e Actions.
- [ ] Qualquer serviço que não caiba na meta aparece como risco explícito, com alternativa ou aceitação registrada.
