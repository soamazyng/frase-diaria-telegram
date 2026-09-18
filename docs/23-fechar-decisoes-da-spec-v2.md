# Fechar decisões abertas da spec v2

## Comportamento

Nenhuma mudança de comportamento do bot — este ticket é só documental. Ele fecha as
decisões que a spec v2 (`.scratch/v2-telegram-bot.md`) tinha deixado em aberto e propaga
o que foi decidido para a spec v1 (`contextIA/Spec-Frase-Diaria-Telegram.md`), que é a
fonte de verdade de vocabulário, fora de escopo e critérios de aceite.

## Decisões fechadas

- **Configuração dos destinatários:** um único parâmetro SSM, `telegram-chat-ids`
  (plural), com os chat_ids separados por vírgula — não um parâmetro por destinatário.
  Ele substitui o `telegram-chat-id` (singular) atual; o ticket 24 é quem lê e passa a
  usar esse parâmetro. O antigo só é removido depois que o novo estiver confirmado em
  produção (ticket 27) — trocar segredo em uso sem essa ordem arrisca uma janela sem
  nenhum destinatário autorizado.
- **Limite de destinatários:** sem teto numérico formal. Registrado como risco a
  observar (tempo de fan-out do envio diário, volume de escritas no DynamoDB), não como
  requisito de validação — o desenho não precisa recusar um número grande, só não foi
  pensado para isso.
- **Seção "Fora de escopo" da spec v1:** reescrita para restringir "múltiplos usuários" a
  um conjunto pequeno e fixo de destinatários privados nomeados pela usuária, deixando
  explícito que grupos, canais públicos e autoinscrição continuam fora.
- **Vocabulário:** "destinatário" entra na spec v1 (seção 2), com a nota de que "conversa
  autorizada" passa a significar "pertence ao conjunto de destinatários autorizados".
- **Critérios de aceite AC32–AC37:** adicionados à spec v1 (seção 5), cobrindo mesma
  frase para todos os destinatários, falha isolada por destinatário, consumo único da
  frase no ciclo, `/status` por destinatário, autenticação do destinatário adicional e
  recusa de quem está fora do conjunto.

## Decisão técnica

**Lista num único parâmetro, não um parâmetro por pessoa.** A alternativa (um parâmetro
nomeado por destinatário, ex. `telegram-chat-id-irmao`) generalizaria pior — cada pessoa
nova exigiria também mudar o código que lê os nomes — mas foi a lista que a usuária
escolheu explicitamente ao decidir entre as duas opções apresentadas; o trade-off
(um parser novo, um jeito silencioso de errar por vírgula a mais/menos) fica registrado
como algo a proteger com teste no ticket 24, não como motivo para reabrir a decisão.

**Sem teto numérico, por design deliberado, não por omissão.** Impor um limite arbitrário
agora exigiria inventar um número sem base — o projeto é para "poucas pessoas da
família", e o risco real (custo, tempo de janela) já está registrado em prosa na spec v2
para ser revisitado se o uso crescer, em vez de codificado como validação que ninguém
sabe justificar hoje.

## Skills aplicadas

`/implement` seguido; `/python-clean-code` não se aplica — mudança é só de documentação
(spec v1, spec v2, ticket), sem nenhum arquivo Python tocado. `/tdd` não se aplica pela
mesma razão. `/code-review` não foi executado por não haver diff de código a revisar;
a revisão real aqui é a própria usuária validando que as decisões registradas
correspondem ao que ela decidiu.

## Testes

Nenhum — ticket documental. `make verificar` não foi executado por não haver mudança de
código; nada em `dominio/`, `aplicacao/`, `infraestrutura/`, `persistencia/`, `notion/`
ou `telegram/` foi tocado.

## Próximo passo

Ticket 24 — autorização e comandos reconhecem múltiplos destinatários, lendo
`telegram-chat-ids` e estendendo `PoliticaDeAcesso` para um conjunto.
