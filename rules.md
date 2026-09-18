# Regras de trabalho

Regras de implementação e armadilhas que **já morderam** neste projeto. O
`CLAUDE.md` descreve o projeto; este arquivo define como trabalhar nele.

## Implementação: Clean Code e skills obrigatórias

**Toda implementação, correção ou refatoração segue este fluxo**, mesmo quando
o pedido não mencionar skills. Aplica-se também à continuação de tickets:

1. Carregue `/implement` de `mattpocock/skills` antes de implementar. O nome
   instalado é `implement`, não `implements`; siga suas instruções por inteiro.
2. Carregue `/python-clean-code` antes de editar Python e aplique suas regras
   durante a implementação e na revisão do diff final. Em mudanças somente de
   infraestrutura ou documentação, consulte-a e registre quais regras Python
   não se aplicam; aplique os princípios gerais pertinentes.
3. Use `/tdd` nas fronteiras acordadas e execute os gates do repositório. Depois
   das últimas correções, reaplique `/python-clean-code` e execute `/code-review`
   nos eixos Standards e Spec. Uma alteração posterior invalida o OK do trecho
   alterado e exige nova verificação.
4. Registre no documento da entrega as skills aplicadas, regras atendidas ou
   exceções justificadas, testes executados e resultado dos dois reviews.
   Atualize `docs/code-review-tickets.md` quando houver ticket. Marque **OK**
   somente após executar a verificação, sem achados impeditivos pendentes.

Skills locais: `.agents/skills/implement/SKILL.md` e
`.agents/skills/python-clean-code/SKILL.md`. Se ausentes, instale a origem
correspondente antes de implementar; se houver bloqueio de acesso ou aprovação,
informe-o e peça direção, sem alegar execução da skill.

Origens: [implement](https://github.com/mattpocock/skills/tree/main/implement) e
[python-clean-code](https://github.com/ertugrul-dmr/clean-code-skills/tree/main/skills/python/python-clean-code).
A segunda é uma adaptação comunitária; não é uma skill de Matt Pocock nem uma
certificação de Robert C. Martin.

**Clean Code de Robert C. Martin (Uncle Bob), aplicado ao projeto:**

- Nomes revelam intenção e efeitos; preserve o vocabulário do domínio em português.
- Funções e módulos têm responsabilidade coesa e um motivo claro para mudar.
  Separe regra de negócio, orquestração e I/O; dependências apontam para dentro.
- Prefira interfaces pequenas, argumentos explícitos e dados tipados. Agrupe
  parâmetros que formam um conceito; evite flags que escolhem comportamentos.
- Elimine duplicação de conhecimento, código morto, comentários óbvios e
  abstrações especulativas. Comentários explicam decisões e restrições.
- Torne estados, pré-condições e efeitos colaterais explícitos; trate erros na
  fronteira adequada, com diagnóstico sanitizado e sem esconder falhas.
- Testes protegem comportamento, limites, repetição e falhas. Refatore em passos
  pequenos, mantendo os testes verdes e preservando alterações de terceiros.

Referências do autor: [responsabilidade única](https://blog.cleancoder.com/uncle-bob/2014/05/08/SingleReponsibilityPrinciple.html)
e [direção das dependências](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html).

**Adaptação explícita:** os comandos `uv`/Makefile e a configuração do projeto
prevalecem sobre exemplos genéricos da skill. Limites de argumentos, número de
acessos encadeados e duração de testes são sinais de revisão, não justificativa
para quebrar contratos existentes, esconder comportamento em wrappers ou trocar
testes de integração por mocks. Qualquer exceção precisa de justificativa local
e avaliação no code-review; não autoriza ignorar a skill. Sua aplicação reforça
a revisão, mas não substitui testes nem garante ausência de bugs.

---

## Segredos

**Trate todo arquivo de credencial como radioativo.** Para inspecionar
`~/.aws/config`, `~/.aws/credentials` ou `.env`, filtre antes de imprimir:
`grep -n '^\[' arquivo` mostra as seções, `sed -E 's/(=).*/\1 <oculto>/'` mostra
as chaves sem os valores.

> Em 2026-09-07 um `cat ~/.aws/config` despejou uma `aws_secret_access_key` no
> histórico da conversa. A chave precisou ser rotacionada.

**Segredos entram no cofre por um terminal separado**, nunca por conversa com
agente. O comando que a usuária digita também vira histórico.

```sh
aws ssm put-parameter --profile perfil-padrao --region us-east-1 \
  --name /frase-diaria/<nome> --type SecureString --value 'VALOR' --overwrite
```

**Valores que o agente pode gerar, o agente gera** — direto para o cofre, sem
passar pela conversa: `--value "$(openssl rand -hex 32)"`.

**Para usar um segredo num comando**, leia para variável, use, e descarte:
`TOKEN=$(aws ssm get-parameter ... --output text)` … `unset TOKEN`. Nunca faça
`echo` do valor.

**Erros que carregam URL vazam credencial.** O token do Telegram viaja na URL da
Bot API, então `urllib.error.HTTPError` o carrega. O padrão do projeto está em
`telegram/canal.py`: converter para um erro próprio com só o código HTTP, e
`raise ... from None` para cortar o encadeamento. Ao integrar qualquer API com
credencial na URL, repita esse padrão e escreva o teste que falha se o segredo
reaparecer na mensagem.

---

## AWS: sonde antes de agir

**O teste real vence a simulação.** `iam:SimulatePrincipalPolicy` ignora
políticas herdadas de grupo e relata `implicitDeny` para ações que funcionam.

> Ele reportou API Gateway negado; a chamada real foi autorizada. Confiar nele
> teria gerado um pedido de permissão desnecessário à usuária.

**Sonde permissão de escrita com entrada inválida.** A AWS autoriza antes de
validar, então `AccessDenied` significa sem permissão e um erro de validação
significa permissão concedida — sem criar nada.

**A exceção é `iam:CreateOpenIDConnectProvider`: ela não valida o thumbprint.**
Uma sonda com valor inválido **cria o provedor de verdade**.

> Foi o que aconteceu: o provedor `token.actions.githubusercontent.com` nasceu de
> uma sonda e teve de ser removido. Antes de sondar criação numa API nova, liste
> os recursos existentes; depois de sondar, liste de novo e compare.

**A mensagem de negativa diz de onde vem o bloqueio.** `because no identity-based
policy allows the action` significa que falta permissão no usuário — anexar a
policy resolve. Uma negativa de Service Control Policy cita explicitamente o
*explicit deny in a service control policy*, e aí nem o root da conta resolve.
Ler a frase antes de propor solução economiza uma rodada inteira.

**Perfis no `~/.aws/config` exigem o prefixo `profile`**: `[profile nome]`. Só o
`default` dispensa. Uma seção `[nome]` ali é invisível ao CLI, que responde
`could not be found` como se o perfil não existisse.

**`TransactWriteItems`/`TransactGetItems` não bastam para um item
`ConditionCheck`.** A AWS trata cada item de uma transação como uma ação IAM
própria: `Put`→`dynamodb:PutItem`, `Update`→`dynamodb:UpdateItem`, e um item
do tipo `ConditionCheck` (checar sem escrever) exige `dynamodb:ConditionCheckItem`
à parte — o wrapper da transação autorizado não cobre isso.

> A diária de 2026-09-18 não chegou: toda tentativa de entrega falhava
> deterministicamente com `AccessDeniedException` em `TransactWriteItems`,
> mascarada como "erro de integração" genérico. `ReservaTransacional` (ticket
> 09) nunca precisou de `ConditionCheckItem` porque embute a condição direto
> no `Put`/`Update`; só o padrão de transação por parte em
> `persistencia/pedidos.py` (`ConditionCheck` separado, para checar o lease do
> pedido sem escrevê-lo) precisa — e a policy nunca ganhou essa ação quando
> esse padrão foi introduzido. Ao adicionar um item `ConditionCheck` numa
> transação nova, adicionar `dynamodb:ConditionCheckItem` à policy no mesmo
> commit, não depois.

**Diagnosticar produção rodando código localmente não prova que a Lambda
funciona.** A credencial de desenvolvedor (`perfil-padrao`) é um principal IAM
diferente da role de execução da função — pode ter permissão que a role real
não tem.

> Foi assim que o achado acima ficou escondido por um tempo: invocações
> manuais do worker (via `montar_processar_pedido().executar(...)` local)
> nunca bateram no mesmo `AccessDeniedException` das automáticas, porque a
> credencial de dev tinha `dynamodb:ConditionCheckItem` e a role do Lambda
> não. Um "funcionou pra mim" rodando local não descarta um problema de IAM —
> só o CloudWatch da própria função (ou testar assumindo a role real) prova
> isso.

---

## Publicar

**Exercite o critério, não o inspecione.** Ler o YAML e concluir que os dados
sobrevivem é uma afirmação sobre texto. O que vale: gravar um item, republicar,
ler o item de volta — e limpar o dado de teste depois.

**Dependências vão para `aarch64-manylinux2014`, não para a máquina.** Um
`_pydantic_core` de macOS passa no build e quebra **em execução**. Confira o
artefato antes de publicar:

```sh
file .aws-sam/build/Funcao/pydantic_core/_pydantic_core*.so   # esperado: ELF ARM aarch64
```

**A Lambda cacheia segredos por container** (`lru_cache` em
`infraestrutura/composicao.py`). Mudar um parâmetro do SSM só vale de imediato
depois de republicar; sem isso, containers quentes seguem com o valor antigo.

**Limpe o que a verificação criou.** Itens de teste na tabela e recursos de sonda
poluem uma base cujo histórico é o produto.

---

## O que os testes não pegam

**Configuração passa por qualquer suíte.** Um `chat_id` errado, um nome de
variável de ambiente divergente, um ARN trocado — os testes seguem verdes porque
o defeito não está no código.

> O `chat_id` informado era o id do bot. Os 72 testes passavam; o bot recusaria
> todas as mensagens da usuária, silenciosamente, porque a recusa é por design
> silenciosa. Só `getMe` revelou.

Confirme todo valor de configuração contra a API real que o consome, e prenda o
que der em teste — como `test_configuracao.py` faz com o nome da variável de
versão, de que o AC21 depende.

**Um guarda que nunca falhou não guarda nada.** Ao criar um teste que protege uma
invariante, quebre a invariante de propósito, veja o teste falhar com a mensagem
certa, e restaure.

> Foi assim que `test_arquitetura.py` ganhou confiança: um `import fastapi` no
> domínio, teste vermelho, restauração.

---

## Padrões já decididos no código

Ao estender qualquer um destes, siga o que existe.

**Idempotência é escrita condicional.** Ler-antes-de-gravar não protege: duas
execuções simultâneas leem "não existe" e ambas gravam. O padrão está em
`persistencia/comandos.py` — `ConditionExpression="attribute_not_exists(pk)"`,
tratando a recusa como "já conhecido".

**A ordem da validação é propriedade de segurança.** O segredo é conferido antes
do `chat_id` para que a resposta não vire oráculo da configuração: quem não tem o
segredo não pode descobrir a conversa autorizada comparando respostas. Compare
segredos com `hmac.compare_digest`. Ver `dominio/autorizacao.py`.

**Status HTTP governa reentrega do Telegram.** 200 encerra, 5xx faz reentregar.
Devolva 200 para o que não muda com nova tentativa — recusa de acesso, update
irrelevante, corpo inválido — e 5xx só quando reentregar tem chance de dar certo,
como falha de persistência. A tabela completa está em `docs/04-webhook-telegram.md`.

**Persista antes de confirmar.** Responder à usuária sem ter gravado deixa um
comando respondido porém não registrado, que volta na reentrega e é respondido de
novo.

**Domínio e aplicação não conhecem framework nem nuvem.** `test_arquitetura.py`
falha se `fastapi`, `mangum`, `starlette`, `boto3` ou `botocore` aparecerem em
`dominio/` ou `aplicacao/`. Quando surgir a tentação de importar um deles ali, o
que está errado é o desenho: crie uma porta em `aplicacao/portas.py` e o
adaptador em `infraestrutura/`.

---

## Custo é decisão de design

**O GitHub Actions arredonda cada execução para 1 minuto cheio.** O intervalo de
um workflow periódico é, portanto, uma decisão de custo antes de ser de
conveniência: a cada 5 minutos dá 8.640 minutos/mês contra os 3.000 do plano Pro
— cerca de US$34/mês, mais caro que toda a infraestrutura AWS somada. O
reconciliador de publicações ficou de hora em hora por isso.

**Antes de adicionar um serviço AWS, verifique se ele tem franquia permanente.**
A conta já passou dos 12 meses, então só vale o *Always Free*. Lambda, DynamoDB e
EventBridge Scheduler estão cobertos com folga; API Gateway custa centavos
no volume do projeto. Registre qualquer novidade em `docs/01-custo-e-elegibilidade.md`.

**Prefira SSM Parameter Store a Secrets Manager**: gratuito contra US$0,40 por
segredo/mês, com o mesmo controle por IAM.

---

## Telegram

**`getUpdates` não convive com um webhook registrado.** Para depurar com ele:
`deleteWebhook`, investigue, `setWebhook` de volta — e não deixe o bot sem
webhook ao encerrar a sessão.

**O id do bot não é o `chat_id` da conversa.** O BotFather exibe o id do bot em
destaque, e confundi-los deixa o bot recusando tudo. O `chat_id` da usuária sai de
`message.chat.id`, ou de `getMe` por eliminação: se os dois números coincidem,
está errado.

---

## Entregar

Cada sessão cabe em menos de duas horas da usuária e fecha explicando **o
comportamento implementado, a decisão técnica, o que os testes demonstram e o
próximo passo** — nessa ordem, porque é a ordem em que ela decide se aceita.

Toda mudança mapeia para um AC da seção 5 da spec. Uma mudança que não mapeia é
escopo novo, e escopo novo é decisão da usuária.

**Relate o que aconteceu, incluindo o que deu errado.** Um recurso criado por
engano, uma sonda que mentiu, um critério que ficou por fazer — dizer isso na
hora custa um parágrafo; descobrir depois custa confiança.
