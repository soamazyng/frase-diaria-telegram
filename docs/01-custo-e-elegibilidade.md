# Elegibilidade e estimativa de custo — AWS e GitHub

**Data da consulta:** 2026-09-07
**Ticket:** 01 — Elegibilidade e estimativa de custo AWS/GitHub
**Meta:** custo recorrente R$0, sem promessa de gratuidade.

> Estado: **concluído** em 2026-09-07. Conta, região, identidade e plano
> confirmados; permissões verificadas contra a conta real; riscos resolvidos ou
> registrados.

## 1. Identidade e região

| Item | Valor |
|---|---|
| Conta AWS | **712790115760** ✓ |
| Região | **us-east-1** ✓ |
| Identidade disponível | `arn:aws:iam::712790115760:user/aws-developer-group` |
| Identidade para bootstrap | a acima, já com permissões suficientes ✓ |
| Perfil local | `perfil-padrao` (no `~/.aws/config`) |
| Conta GitHub | `soamazyng` (pessoal, criada em 2010-10-17) |
| Repositório | `soamazyng/frase-diaria-telegram` — privado ✓ |
| Plano do GitHub | **Pro** ✓ (já assinado, US$4/mês, anterior ao projeto) |

A conta 712790115760 é a mesma do perfil `bedrock-curso`, originalmente de curso.
A escolha foi da usuária, ciente de que o billing fica misturado com material de
estudo.

`us-east-1` é proposta por ser a região mais barata e com a maior cobertura de
serviços. A latência é irrelevante para um bot que envia uma mensagem por dia;
`sa-east-1` (São Paulo) custa consistentemente mais caro pelo mesmo resultado.

## 2. Volume estimado de uso

Base do cálculo, por mês:

| Origem | Invocações/mês | Como se chega ao número |
|---|---|---|
| Envio diário | 30 | 1 por dia |
| Reconciliador de pedidos | 8.640 | a cada 5 min: 288/dia × 30 |
| Webhook (`/frase`, `/status`, `/start`) | ~60 | estimativa de uso pessoal |
| **Total Lambda** | **~8.730** | |

O reconciliador de pedidos domina o volume: sozinho é 99% das invocações.

## 3. Elegibilidade item a item — AWS

| Serviço | Franquia | Uso estimado | % da franquia | Custo |
|---|---|---|---|---|
| Lambda (invocações) | 1M/mês *always free* | ~8.730 | 0,9% | R$0 |
| Lambda (computação) | 400.000 GB-s *always free* | ~1.100 GB-s | 0,3% | R$0 |
| EventBridge Scheduler | 14M/mês, **permanente** | ~8.670 | 0,06% | R$0 |
| DynamoDB (armazenamento) | 25 GB *always free* | poucos MB | <0,1% | R$0 |
| DynamoDB (requisições) | on-demand não tem franquia | ~100k req | — | ~US$0,01 |
| API Gateway HTTP API | esgotada (conta > 12 meses) | ~100 req | — | ~US$0,0001 |
| S3 (cache de mídia) | 5 GB / 20k GET / 2k PUT | poucos MB | <0,1% | ~R$0 |
| CloudWatch Logs | 5 GB de ingestão | baixo, retenção 14 dias | baixo | ~R$0 |
| Tráfego de saída | 100 GB/mês | desprezível | <0,1% | R$0 |
| SSM Parameter Store (Standard) | sem cobrança por parâmetro | 4 parâmetros | — | R$0 |

**Conclusão:** a operação do bot cabe na franquia *permanente* (Always Free), que
não depende da idade da conta. Os serviços que dependem de franquia de 12 meses
— API Gateway e S3 — custam centavos mesmo **sem** franquia nenhuma, porque o
volume é irrisório.

### O Free Tier da AWS mudou

Contas abertas a partir de **15/07/2025** não recebem franquia por serviço: ganham
até US$200 em créditos e um Free Plan de 6 meses. Contas anteriores mantêm o
modelo de 12 meses. **O Always Free (Lambda, DynamoDB, Scheduler) vale para todas
as contas, novas e antigas** — e é nele que este projeto se apoia.

## 4. Elegibilidade — GitHub Actions

A conta está no plano **Pro**, que inclui **3.000 minutos/mês** para repositórios
privados e 1 GB de artefatos. O excedente custa US$0,006/min (Linux). O GitHub
arredonda cada execução para **1 minuto cheio**, o que torna o intervalo de um
workflow periódico uma decisão de custo, não de conveniência.

| Intervalo do reconciliador de publicações | Execuções/mês | Minutos | Cabe em 3.000? |
|---|---|---|---|
| 5 min | 8.640 | 8.640 | ✗ ~US$34/mês de excedente |
| 15 min | 2.880 | 2.880 | ⚠ quase nada sobra |
| 30 min | 1.440 | 1.440 | ✓ |
| **1 hora — decidido** | **720** | **720** | ✓ com folga |

Orçamento mensal com o intervalo decidido:

| Uso | Minutos |
|---|---|
| Reconciliador de publicações (1h) | 720 |
| Pipeline por push em `develop` (~20 × 8 min) | ~160 |
| **Total** | **~880 de 3.000 (29%)** |

Sobram cerca de 2.100 minutos. Se a recuperação de meia em meia hora passar a
parecer valiosa, o orçamento comporta (1.600 de 3.000); a decisão de 1 hora
permanece por conservadorismo, não por limite.

**Consumo atual de Actions:** praticamente nulo — 4 minutos em março e 1 em agosto
de 2026, ambos integralmente cobertos pela franquia. Nenhum valor líquido foi
cobrado.

> **Não confundir os dois reconciliadores.** O de *pedidos* roda em Lambda a cada
> 5 minutos e é praticamente grátis (seção 3). O de *publicações* roda em GitHub
> Actions e é o caro. A spec só propôs intervalo para o primeiro.

## 5. Riscos e incompatibilidades registrados

### R1 — Proteção de `main`: **RESOLVIDO**

O risco supunha plano Free, em que repositório privado permite *configurar* branch
protection mas não a aplica — o que inviabilizaria o AC29.

**A conta está no plano Pro**, que aplica branch protection em repositórios
privados. O AC29 é atendível como especificado, sem tornar o repositório público e
sem relaxar a exigência.

Quanto ao custo: o Pro custa US$4/mês, **mas já era assinado antes deste projeto**.
Não é despesa nova nem atribuível ao bot, então a meta de custo recorrente
adicional R$0 segue de pé. Vale registrar a dependência: se o plano for rebaixado
para Free no futuro, o AC29 deixa de ser atendível e o ticket 21 precisa ser
revisto.

### R2 — Armazenamento de segredos: **RESOLVIDO, gratuito**

`ssm:PutParameter` e `ssm:GetParameter` passaram a ser permitidos. O **SSM
Parameter Store (Standard)** guarda os quatro valores — token do Notion, token do
Telegram, `chat_id` e segredo do webhook — como `SecureString`, **sem custo por
parâmetro**, com controle de acesso por IAM.

Secrets Manager continua disponível como alternativa, mas custaria ~US$0,40 por
segredo/mês sem trazer vantagem para este caso. Parameter Store é a escolha, a ser
declarada no ticket 03.

### R3 — Permissões da identidade: **RESOLVIDO**

Depois de a usuária anexar `docs/aws-policy-bootstrap.json`, a verificação de
2026-09-07 confirma tudo que os tickets 03 e 16 exigem:

| Ação | Situação |
|---|---|
| `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `iam:PassRole` | permitido |
| `iam:CreateOpenIDConnectProvider` | permitido |
| `cloudformation:CreateStack`, `CreateChangeSet`, `ExecuteChangeSet` | permitido |
| `lambda:CreateFunction`, `AddPermission`, `TagResource` | permitido |
| `dynamodb:CreateTable`, `s3:CreateBucket`, `s3:PutObject` | permitido |
| `scheduler:CreateSchedule`, `logs:CreateLogGroup` | permitido |
| `apigatewayv2:CreateApi` | permitido |
| `ssm:PutParameter`, `GetParameter` | permitido |
| `freetier:GetFreeTierUsage` | permitido |

**Nota de método.** `iam:SimulatePrincipalPolicy` reportou `implicitDeny` para o
API Gateway, mas a chamada real foi autorizada — o simulador não enxergou as
políticas herdadas do grupo `developer`, ao qual o usuário pertence. Quando as
duas fontes divergirem, **vale o teste real**; a simulação subestima o que o
usuário pode fazer.

**Incidente registrado.** Ao sondar `iam:CreateOpenIDConnectProvider`, a chamada
foi feita com um thumbprint propositalmente inválido para provocar erro de
validação. A AWS **aceitou o valor** e criou o provedor
`token.actions.githubusercontent.com` com thumbprint inválido. O recurso foi
identificado e removido no mesmo dia; a conta terminou com zero provedores. A
lição é que `CreateOpenIDConnectProvider` não valida o formato do thumbprint —
sondar criação com entradas inválidas não é seguro para essa API.

### R6 — Hipótese de Service Control Policy: **DESCARTADA**

A conta tem `AWSServiceRoleForOrganizations` e `AWSServiceRoleForSSO`, o que levantou
a suspeita de uma SCP negando escrita em IAM — caso em que nem o root da conta
resolveria.

**A mensagem de erro da AWS descarta a hipótese.** Ao negar, ela diz:

> `is not authorized to perform: iam:GetUser ... because **no identity-based policy
> allows** the iam:GetUser action`

Quando a negativa vem de uma SCP, a AWS usa outra formulação, citando
explicitamente o *explicit deny in a service control policy*. A formulação obtida
indica ausência de permissão na política de identidade, não bloqueio
organizacional.

**Conclusão:** basta anexar as permissões ao usuário. O JSON pronto está em
`docs/aws-policy-bootstrap.json`.

## 6. Pendências que dependem da usuária

- [x] Rotacionar a access key exposta em 2026-09-07 — feito pela usuária.
- [x] Definir a conta AWS: **712790115760**.
- [x] Corrigir a seção do perfil no `~/.aws/config` para `[profile perfil-padrao]`.
- [x] Confirmar a região: **us-east-1**.
- [x] B1 — `docs/aws-policy-bootstrap.json` anexado ao usuário; permissões
      verificadas contra a conta real.
- [x] B2 — hipótese de SCP descartada pela mensagem de erro da AWS (risco R6).
- [x] Plano do GitHub confirmado: **Pro**, 3.000 min/mês (2026-09-07).
- [x] Alertas de billing na AWS — já configurados pela usuária.

### Pendência menor: higiene de credenciais

As chaves do `perfil-padrao` estão no `~/.aws/config`. O lugar convencional é o
`~/.aws/credentials`; o `config` guarda região e perfis. Não é urgente, mas
convém mover quando houver oportunidade.

## 7. Como acompanhar o consumo depois

**AWS**
- Billing and Cost Management → *Free tier* mostra o uso contra cada franquia.
- Billing → *Budgets*: alertas **já configurados** pela usuária.
- Cost Explorer, agrupado por serviço, para achar quem cresceu.

**GitHub**
- Settings → Billing and plans → *Actions* mostra os minutos consumidos no mês.
- Os minutos zeram todo dia 1º.

## Fontes

Consultadas em 2026-09-07:

- [Amazon EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/)
- [Amazon API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/)
- [AWS Free Tier em 2026 — o que mudou](https://infratally.com/articles/aws-free-tier-2026/)
- [About protected branches — GitHub Docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
