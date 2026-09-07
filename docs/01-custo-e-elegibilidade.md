# Elegibilidade e estimativa de custo — AWS e GitHub

**Data da consulta:** 2026-09-07
**Ticket:** 01 — Elegibilidade e estimativa de custo AWS/GitHub
**Meta:** custo recorrente R$0, sem promessa de gratuidade.

> Estado: **parcial.** Conta, região e identidade estão confirmadas, mas a
> identidade disponível **não tem as permissões necessárias** para o bootstrap
> nem para o armazenamento de segredos — ver seção 6.

## 1. Identidade e região

| Item | Valor |
|---|---|
| Conta AWS | **712790115760** ✓ |
| Região | **us-east-1** ✓ |
| Identidade disponível | `arn:aws:iam::712790115760:user/aws-developer-group` |
| Identidade para bootstrap | ⚠ **a acima não serve** — ver seção 6, B1 |
| Perfil local | `perfil-padrao` (no `~/.aws/config`) |
| Conta GitHub | `soamazyng` (pessoal, criada em 2010-10-17) |
| Repositório | `soamazyng/frase-diaria-telegram` — privado ✓ |
| Plano do GitHub | **PENDENTE** — token do `gh` sem escopo `user` |

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
| API Gateway HTTP API | 1M/mês nos 12 primeiros meses | ~100 req | <0,1% | ~US$0,0001 |
| S3 (cache de mídia) | 5 GB / 20k GET / 2k PUT | poucos MB | <0,1% | ~R$0 |
| CloudWatch Logs | 5 GB de ingestão | baixo, retenção 14 dias | baixo | ~R$0 |
| Tráfego de saída | 100 GB/mês | desprezível | <0,1% | R$0 |
| Segredos / KMS | **decisão em aberto** | — | — | ver seção 5 |

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

O plano Free dá **2.000 minutos/mês** em repositório privado, e o GitHub arredonda
cada execução para **1 minuto cheio**. Isso torna o intervalo de um workflow
periódico uma decisão de custo, não de conveniência.

| Intervalo do reconciliador de publicações | Execuções/mês | Minutos | Cabe? |
|---|---|---|---|
| 5 min | 8.640 | 8.640 | ✗ ~US$53/mês de excedente |
| 15 min | 2.880 | 2.880 | ✗ estoura |
| 30 min | 1.440 | 1.440 | ⚠ sobram ~560 min |
| **1 hora — decidido** | **720** | **720** | ✓ |

Orçamento mensal de Actions com o intervalo decidido:

| Uso | Minutos |
|---|---|
| Reconciliador de publicações (1h) | 720 |
| Pipeline por push em `develop` (~20 × 8 min) | ~160 |
| **Total** | **~880 de 2.000** |

Sobra em torno de 1.100 minutos de folga para pushes extras e reexecuções.

> **Não confundir os dois reconciliadores.** O de *pedidos* roda em Lambda a cada
> 5 minutos e é praticamente grátis (seção 3). O de *publicações* roda em GitHub
> Actions e é o caro. A spec só propôs intervalo para o primeiro.

## 5. Riscos e incompatibilidades registrados

### R1 — Proteção de `main` é incompatível com o plano Free (ABERTO)

Em repositório **privado no plano Free**, o GitHub permite *configurar* branch
protection mas **não a aplica**. O AC29 exige que a proteção seja exercitada no
repositório real e impeça merge com checks falhos ou ausentes.

Alternativas:

1. **Manter Free** e registrar o AC29 como não atendível no plano atual. Custo
   recorrente segue R$0; o merge continua manual, sem trava técnica.
2. **Assinar GitHub Pro** (US$4/mês, ~R$22). O AC29 passa de verdade e a meta R$0
   vira "custo aceito e registrado".

Tornar o repositório público **não é alternativa**: a spec proíbe explicitamente.

**Decisão adiada pela usuária.** Trava de fato apenas no ticket 21.

### R2 — Armazenamento de segredos: SSM indisponível, Secrets Manager custa (ABERTO)

São quatro valores: token do Notion, token do Telegram, `chat_id` e segredo do
webhook.

| Opção | Disponível? | Custo mensal |
|---|---|---|
| SSM Parameter Store (Standard) | **não** — `ssm:*` negado | seria R$0 |
| Secrets Manager, 1 segredo JSON com os 4 valores | sim | ~US$0,40 (~R$2,20) |
| Secrets Manager, 4 segredos separados | sim | ~US$1,60 (~R$8,80) |
| Variáveis de ambiente da Lambda | sim | **R$0** |

O caminho que seria gratuito (Parameter Store) está bloqueado pelas permissões. A
opção gratuita restante é usar variáveis de ambiente da função, cifradas em repouso
com chave gerenciada pela AWS e populadas por parâmetro do SAM — os valores nunca
entram no Git. É aceitável para um bot de usuária única, com a ressalva de que
variáveis de ambiente aparecem para quem tiver `lambda:GetFunctionConfiguration`.

Se as permissões de SSM forem liberadas, Parameter Store volta a ser a melhor
opção: gratuito e com o mesmo modelo de acesso por IAM.

### R3 — A identidade não pode criar recursos de IAM (BLOQUEANTE)

Sondagem refeita em 2026-09-07, depois de a usuária ampliar as permissões. As
sondas de criação usaram entradas inválidas de propósito, para que a AWS
autorizasse antes de validar: **nenhum recurso foi criado** (confirmado por
`list-open-id-connect-providers` e `list-secrets`, ambos vazios ao final).

| Ação | Antes | Agora |
|---|---|---|
| `cloudformation:CreateStack` | — | **permitido** |
| `secretsmanager:ListSecrets` / `CreateSecret` | negado | **permitido** |
| `iam:ListOpenIDConnectProviders` | negado | **permitido** |
| `iam:ListRoles`, `iam:GetRole` | permitido | permitido |
| **`iam:CreateRole`** | — | **NEGADO** |
| **`iam:CreateOpenIDConnectProvider`** | negado | **NEGADO** |
| **`iam:AttachRolePolicy`** | — | **NEGADO** |
| `iam:SimulatePrincipalPolicy`, `ListAttachedUserPolicies` | negado | NEGADO |
| `ssm:DescribeParameters` | negado | NEGADO |
| `freetier:GetFreeTierUsage` | negado | NEGADO |
| `organizations:DescribeOrganization` | — | NEGADO |

As leituras melhoraram, mas **a escrita em IAM continua negada** — e é ela que os
tickets 03 e 16 exigem.

**Ticket 16 (bootstrap OIDC): impossível.** Exige `CreateOpenIDConnectProvider` e
`CreateRole`, ambos negados. Como o 16 bloqueia 17 → 18 → 19 → 20 → 21, a frente
inteira de CI/CD está parada atrás dele.

**Ticket 03 (publicação SAM): bloqueado no caminho normal.** `CreateStack` é
permitido, mas o SAM cria a execution role da Lambda e esbarra em `CreateRole`.
Existe um contorno: a conta tem três roles com principal `lambda.amazonaws.com`
(`Lambda_Execution_Role`, `hello-world-python-role-rwu4pmmk`,
`serverless-rest-api-with-dynamodb-dev-us-east-2-lambdaRole`) e o SAM aceita uma
role explícita em vez de criar a sua. O contorno tem dois defeitos: depende de
`iam:PassRole` (não testado) e viola a exigência da spec de "permissões
específicas por função", porque reaproveita uma role de tutorial com escopo
desconhecido. Serve para destravar um experimento, não para a versão final.

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
- [ ] **B1 — anexar `docs/aws-policy-bootstrap.json` ao usuário
      `aws-developer-group`.** Sem isso os tickets 03 e 16 não avançam. Duas
      tentativas de ajuste manual não surtiram efeito; o JSON existe para
      eliminar a chance de faltar alguma ação.
- [x] B2 — hipótese de SCP descartada pela mensagem de erro da AWS (risco R6).
- [ ] Confirmar o plano do GitHub. O token tem `gist, read:org, repo, workflow`,
      mas falta `user`; o refresh ainda não foi aplicado.
- [x] Alertas de billing na AWS — já configurados pela usuária.

### Higiene de credenciais pendente

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
