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

### R2 — Armazenamento de segredos ainda não escolhido (ABERTO)

Secrets Manager cobra por segredo/mês e não tem franquia permanente. SSM Parameter
Store (Standard) não cobra pelo parâmetro. São necessários quatro valores: token do
Notion, token do Telegram, `chat_id` e segredo do webhook. A escolha é uma das
decisões em aberto do CLAUDE.md e entra no ticket 03.

### R3 — A identidade disponível não cobre o projeto (BLOQUEANTE)

Sondagem feita em 2026-09-07 contra `user/aws-developer-group`:

| Serviço | Resultado |
|---|---|
| CloudFormation, Lambda, DynamoDB, S3 | permitido |
| API Gateway v2, EventBridge Scheduler, CloudWatch Logs | permitido |
| `iam:ListRoles` | permitido |
| `iam:ListAttachedUserPolicies`, `ListOpenIDConnectProviders` | **negado** |
| `iam:SimulatePrincipalPolicy` | **negado** |
| SSM Parameter Store | **negado** |
| Secrets Manager | **negado** |
| `freetier:GetFreeTierUsage` | **negado** |

Consequências diretas:

1. **Ticket 16 (bootstrap OIDC) não é executável com esta identidade.** Criar o
   provedor OIDC e as roles exige permissões de IAM que ela não tem. A spec já
   avisa que "um pipeline sem confiança não cria a própria autorização": o
   bootstrap precisa de uma identidade **já autorizada**, e esta não é.
2. **Ticket 03 (publicação SAM) provavelmente falha.** O SAM cria roles IAM para a
   função Lambda; sem `iam:CreateRole` o deploy para no meio.
3. **O risco R2 fica sem saída pelos caminhos usuais.** Nem Parameter Store nem
   Secrets Manager estão acessíveis.

Alternativas, da mais barata para a mais cara:

- **Conceder permissões ao usuário atual** usando o root ou um admin da conta
  712790115760. Resolve tudo sem criar conta nova, se a usuária tiver esse acesso.
- **Usar outra identidade da mesma conta** que já tenha poder de IAM, apenas para
  o bootstrap (que roda uma vez), mantendo a atual para o dia a dia.
- **Criar uma conta AWS dedicada**, onde a usuária é root por construção. Também
  separa o billing do material de curso.

### R5 — Elegibilidade de franquia não verificável nesta conta (ABERTO)

`freetier:GetFreeTierUsage` está negado, então não foi possível confirmar pela API
se a conta ainda tem franquia de 12 meses ou apenas o Always Free. Como a conta
vem de um curso, o mais provável é que já tenha passado dos 12 meses.

Isso **não muda a conclusão**: a estimativa da seção 3 mostra que o bot cabe no
Always Free, e os serviços de franquia limitada custam centavos sem ela.

### R4 — VPC e NAT

**Não serão usados.** Lambda, DynamoDB, S3 e API Gateway são acessados pelos
endpoints públicos dos serviços com IAM. Um NAT Gateway custaria cerca de US$32/mês
sozinho — mais que todo o resto do projeto somado. Nenhum requisito da spec exige
rede privada.

## 6. Pendências que dependem da usuária

- [x] Rotacionar a access key exposta em 2026-09-07 — feito pela usuária.
- [x] Definir a conta AWS: **712790115760**.
- [x] Corrigir a seção do perfil no `~/.aws/config` para `[profile perfil-padrao]`.
- [x] Confirmar a região: **us-east-1**.
- [ ] **B1 — resolver as permissões de IAM** (risco R3). Sem isso os tickets 03 e
      16 não avançam.
- [ ] Confirmar o plano do GitHub — exige `gh auth refresh -h github.com -s user`.
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
