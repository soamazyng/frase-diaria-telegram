# Elegibilidade e estimativa de custo — AWS e GitHub

**Data da consulta:** 2026-09-07
**Ticket:** 01 — Elegibilidade e estimativa de custo AWS/GitHub
**Meta:** custo recorrente R$0, sem promessa de gratuidade.

> Estado: **parcial.** Os itens marcados como PENDENTE dependem de dados da conta
> AWS que ainda não foi definida. Tudo que não depende da conta está fechado.

## 1. Identidade e região

| Item | Valor |
|---|---|
| Conta AWS | **PENDENTE** — ver seção 6 |
| Região | **PENDENTE** — proposta: `us-east-1` |
| Identidade para bootstrap | **PENDENTE** |
| Conta GitHub | `soamazyng` (pessoal, criada em 2010-10-17) |
| Repositório | `soamazyng/frase-diaria-telegram` — privado ✓ |
| Plano do GitHub | **PENDENTE** — o token do `gh` não tem escopo `user` |

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

### R3 — Conta AWS não definida (ABERTO)

Ver seção 6.

### R4 — VPC e NAT

**Não serão usados.** Lambda, DynamoDB, S3 e API Gateway são acessados pelos
endpoints públicos dos serviços com IAM. Um NAT Gateway custaria cerca de US$32/mês
sozinho — mais que todo o resto do projeto somado. Nenhum requisito da spec exige
rede privada.

## 6. Pendências que dependem da usuária

- [ ] **Rotacionar a access key exposta** (`AKIA2L5M2AWYAO5YEYYL`), que apareceu em
      texto plano no `~/.aws/config` durante a sessão de 2026-09-07.
- [ ] Definir a conta AWS do projeto e registrar o número aqui.
- [ ] Corrigir o perfil no `~/.aws/config`: a seção precisa ser
      `[profile <nome>]`, não `[<nome>]`, e credenciais pertencem ao
      `~/.aws/credentials`.
- [ ] Confirmar a região.
- [ ] Confirmar o plano do GitHub — exige `gh auth refresh -h github.com -s user`.

## 7. Como acompanhar o consumo depois

**AWS**
- Billing and Cost Management → *Free tier* mostra o uso contra cada franquia.
- Billing → *Budgets*: criar um orçamento de **US$1/mês** com alerta por e-mail.
  É o que transforma "meta R$0" em algo que avisa quando é violado.
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
