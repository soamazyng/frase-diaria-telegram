# Autorização e comandos reconhecem múltiplos destinatários

## Comportamento

`/frase`, `/status` e `/start` passam a funcionar para qualquer chat_id dentro de um
conjunto configurado de destinatários autorizados, não só para um único chat_id fixo.
Uma conversa fora do conjunto — ou de grupo, independentemente do chat_id — continua
sendo recusada silenciosamente: sem resposta, sem pedido criado, exatamente como hoje.

O conjunto de destinatários vem de um único parâmetro SSM novo, `telegram-chat-ids`
(lista separada por vírgula) — decisão fechada no ticket 23. O disparo agendado da
diária **não muda neste ticket**: `montar_criar_diaria()` continua lendo o parâmetro
singular `telegram-chat-id`, porque migrar a diária para múltiplos destinatários exige
mudar `Pedido`/`CriarDiaria` para carregar vários destinatários com uma única reserva de
frase — isso é o ticket 25.

## Decisão técnica

**`PoliticaDeAcesso.chat_id_autorizado: int` virou `chat_ids_autorizados: frozenset[int]`.**
`conferir_conversa` passou de igualdade para pertencimento ao conjunto; a ordem de
verificação (segredo antes de conversa, `hmac.compare_digest`) não mudou — é a mesma
proteção contra a resposta virar oráculo da configuração.

**Falhar alto em vez de conjunto vazio.** A primeira versão de `_destinatarios_autorizados`
(`infraestrutura/composicao.py`) aceitava silenciosamente um parâmetro vazio, só de
vírgulas ou só de espaços, devolvendo um conjunto vazio — o que faria `PoliticaDeAcesso`
recusar **todo mundo**, inclusive a usuária, sem nenhum erro visível. Isso foi encontrado
no `/code-review` e corrigido: agora `_destinatarios_autorizados` levanta `ValueError`
nesse caso, na mesma linha do que `rules.md` já registra em "O que os testes não pegam" —
um erro de configuração deve travar alto, não virar uma recusa silenciosa indistinguível
de "funcionando normalmente, mas ninguém está autorizado".

**Migração faseada do parâmetro SSM.** `telegram-chat-ids` (novo) coexiste com
`telegram-chat-id` (antigo) até o ticket 25 migrar a diária e o ticket 27 confirmar tudo
em produção — remover o parâmetro antigo antes disso quebraria o disparo agendado.

## Skills aplicadas

`/implement` e `/python-clean-code` seguidos. `/tdd` aplicado nas fronteiras de
`PoliticaDeAcesso.conferir_conversa` e `ReceberComando.executar`: teste primeiro para o
conjunto vazio (`ValueError`) e para os dois destinatários usando `/frase`/`/status`, depois
a implementação. `/code-review` executado nos eixos Standards e Spec — três achados, os
três corrigidos nesta mesma entrega (ver "Review" abaixo). Nenhuma regra do
`python-clean-code` foi tratada como exceção.

## Testes

- `tests/dominio/test_autorizacao.py`: dois destinatários autorizados, ambos aceitos; um
  terceiro chat_id recusado mesmo com dois autorizados (AC36/AC37).
- `tests/aplicacao/test_receber_comando.py`: `/frase` e `/status` funcionando para os dois
  destinatários configurados, com identidades de pedido distintas; um terceiro chat_id
  continua sem resposta e sem pedido.
- `tests/infraestrutura/test_configuracao.py`: `_destinatarios_autorizados` lendo a lista
  (com e sem espaços, valor único) e falhando com `ValueError` para parâmetro vazio, só de
  vírgulas ou só de espaços.
- `make verificar`: 390 testes, ruff e mypy limpos.

## Review

`/code-review` (Standards e Spec) encontrou três pontos, todos corrigidos nesta entrega:

1. `_destinatarios_autorizados` podia devolver um conjunto vazio e recusar todo mundo
   silenciosamente — corrigido para falhar com `ValueError`.
2. Faltava um teste de `ReceberComando` fim a fim com dois destinatários exercitando
   `/frase` e `/status` — adicionado.
3. A spec v2 (`.scratch/v2-telegram-bot.md`) descrevia o ticket 24 como responsável também
   pela lista de destinatários da diária — corrigida para refletir a divisão real entre os
   tickets 24 (webhook) e 25 (diária).

## Próximo passo

Ticket 25 — diária com múltiplos destinatários: `Pedido.destinatarios`, reserva/consumo
único de frase no ciclo, entrega em fan-out, falha isolada por destinatário.

**Pendência da usuária antes de publicar este ticket:** cadastrar o parâmetro
`telegram-chat-ids` no SSM (pelo terminal dela, fora desta conversa) com pelo menos o
próprio chat_id — sem ele, o webhook fica sem nenhum destinatário autorizado assim que
esta versão for publicada.
