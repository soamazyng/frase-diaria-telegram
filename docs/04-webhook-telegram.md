# Webhook do Telegram

**Ticket:** 04 — Webhook autenticado, `/start` e ajuda

## Segredos

Ficam no SSM Parameter Store como `SecureString`, **fora do Git**:

| Parâmetro | O que é |
|---|---|
| `/frase-diaria/telegram-bot-token` | token do BotFather; dá controle total do bot |
| `/frase-diaria/telegram-chat-id` | a única conversa autorizada |
| `/frase-diaria/webhook-secret` | valor esperado em `X-Telegram-Bot-Api-Secret-Token` |

Gravar um segredo — **de um terminal fora de qualquer sessão de agente**, para que
o valor não fique em histórico de conversa:

```sh
aws ssm put-parameter --profile perfil-padrao --region us-east-1 \
  --name /frase-diaria/telegram-bot-token --type SecureString \
  --value 'VALOR' --overwrite
```

O segredo do webhook não precisa ser escolhido por ninguém:

```sh
aws ssm put-parameter --profile perfil-padrao --region us-east-1 \
  --name /frase-diaria/webhook-secret --type SecureString \
  --value "$(openssl rand -hex 32)" --overwrite
```

> **`chat_id` não é o ID do bot.** O BotFather exibe o ID *do bot* em destaque, e
> é fácil confundir. O `chat_id` da usuária se descobre mandando uma mensagem ao
> bot e lendo `message.chat.id`. Se os dois forem iguais, está errado: o bot
> recusaria todas as mensagens, comparando o remetente consigo mesmo.

## Registrar o webhook

```sh
TOKEN=$(aws ssm get-parameter --profile perfil-padrao --region us-east-1 \
  --name /frase-diaria/telegram-bot-token --with-decryption --query Parameter.Value --output text)
SEGREDO=$(aws ssm get-parameter --profile perfil-padrao --region us-east-1 \
  --name /frase-diaria/webhook-secret --with-decryption --query Parameter.Value --output text)

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H 'Content-Type: application/json' \
  -d "{\"url\":\"https://kamvdtjaw0.execute-api.us-east-1.amazonaws.com/telegram/webhook\",
       \"secret_token\":\"${SEGREDO}\",
       \"allowed_updates\":[\"message\"],
       \"drop_pending_updates\":true}"

unset TOKEN SEGREDO
```

`allowed_updates: ["message"]` reduz o tráfego ao que interessa. `getUpdates` **não
funciona enquanto o webhook estiver registrado** — para depurar com ele, chame
`deleteWebhook` antes e registre de novo depois.

## Como a autenticação decide

A ordem é deliberada:

1. **segredo** do cabeçalho `X-Telegram-Bot-Api-Secret-Token`
2. **tipo** da conversa: só `private`
3. **`chat_id`** autorizado

O segredo vem primeiro para que quem não o tenha não consiga descobrir qual
conversa é a autorizada comparando respostas. A comparação usa
`hmac.compare_digest`, não `==`.

Uma entrada recusada **não recebe resposta e não gera pedido** (AC18). O motivo da
recusa vai para o log; a resposta HTTP nunca o revela.

## Códigos de status e reentrega

O status é a única coisa que o Telegram observa, e governa a reentrega:

| Situação | Status | Por quê |
|---|---|---|
| Comando aceito e registrado | 200 | feito |
| Update já conhecido | 200 | reentrega não deve duplicar |
| Não autorizado | 200 | reentregar não mudaria o resultado |
| Update irrelevante (enquete etc.) | 200 | nunca vai interessar |
| Corpo não é JSON | 200 | não vira válido numa reentrega |
| **Falha ao persistir** | **500** | queremos que o Telegram reentregue |

O comando é gravado **antes** de a resposta confirmar recebimento. Responder à
usuária sem ter registrado deixaria um comando respondido porém não persistido,
que voltaria na reentrega e seria respondido de novo.

## Idempotência

A identidade de um extra é o `update_id` (spec, 4.6). O registro usa escrita
condicional (`attribute_not_exists(pk)`): se o item existe, o DynamoDB recusa e o
comando é reconhecido como já conhecido. Ler antes de gravar não serviria — duas
execuções simultâneas leriam "não existe" e ambas gravariam.

## Sanitização do token

O token do bot faz parte da **URL** da Bot API. Qualquer exceção que carregue a URL
vaza o token nos logs, e é por isso que `telegram/canal.py` converte todo erro em
`ErroDoTelegram` reportando apenas o código HTTP, com `raise ... from None` para
descartar o encadeamento. Há testes que falham se o token reaparecer na mensagem.
