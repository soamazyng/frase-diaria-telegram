# Spec — v2: Múltiplos Destinatários no Telegram

Versão: 1.1
Estado: decisões fechadas pela usuária (ticket 23); pronta para os tickets de implementação (24–27).
Triagem sugerida: ready-for-agent — indicação documental, sem label aplicada a um rastreador (o projeto não tem rastreador configurado — spec original, seção "Dependências e condições de desbloqueio").
Repositório: frase-diaria-telegram (mesmo repositório da spec v1).
Responsável pelo produto e merge: Jay.

### Fontes e precedência

1. Esta spec estende [`contextIA/Spec-Frase-Diaria-Telegram.md`](../contextIA/Spec-Frase-Diaria-Telegram.md) ("spec v1"), que continua sendo a fonte de verdade para tudo que não é mencionado aqui: sincronização com o Notion, formatação e limites de mensagem, janela de agendamento e retentativas, idempotência de extras, publicação e CI/CD, recuperação de versão.
2. Onde esta spec e a v1 conflitarem, esta spec prevalece — mas só nos pontos explicitamente listados na seção "Implementation Decisions" abaixo. Ela não reabre nenhuma decisão da v1 que não seja consequência direta de haver mais de um destinatário.
3. O vocabulário da v1 (seção 2 dela) é herdado por inteiro: **frase**, **coleção válida**, **ciclo**, **pedido de envio**, **tentativa**, **entrega confirmada**, **entrega incerta**, **versão estável**, **versão candidata**. Esta spec acrescenta um único termo novo, **destinatário** (ver abaixo).

## Problem Statement

A usuária recebe uma frase diária no Telegram e quer que o irmão dela também receba — ele gostou da ideia e tem Telegram. Hoje o bot é desenhado para uma única conversa autorizada: um único `chat_id` decide quem recebe a diária, quem pode falar com o bot e quem aparece no histórico. Não existe um jeito de adicionar uma segunda pessoa sem tratá-la como uma conversa qualquer não autorizada (que o bot silenciosamente ignora, por desenho).

## Solution

O bot passa a reconhecer um **conjunto pequeno e fixo de destinatários autorizados** em vez de um único. Todo dia, a mesma frase sorteada é entregue a todos os destinatários autorizados — não frases diferentes por pessoa. Qualquer destinatário autorizado pode usar `/frase` (frase extra, só para ele) e `/status` (diagnóstico da própria entrega). A falha ao entregar a um destinatário não impede nem atrasa a entrega aos demais.

### Vocabulário novo

- **Destinatário:** uma conversa privada autorizada a receber entregas do bot. Antes da v2 existia exatamente um; a partir da v2 existe um conjunto fixo e pequeno, configurado pela usuária. "Conversa autorizada" (spec v1) passa a significar "pertence ao conjunto de destinatários", não mais "é o único chat_id configurado".
- **Entrega ao destinatário:** o envio (bem-sucedido, incerto ou falho) de uma parte de uma frase a um destinatário específico dentro de um pedido. Um mesmo pedido de envio diário produz uma entrega por destinatário; o resultado de uma não determina o resultado das outras.

## User Stories

1. Como usuária, quero que meu irmão receba a mesma frase diária que eu, para compartilharmos a mesma experiência.
2. Como usuária, quero que a frase do dia seja sorteada uma única vez e enviada a todos os destinatários, para que os dois recebam exatamente o mesmo conteúdo no mesmo dia.
3. Como usuária, quero que a entrega ao meu irmão não dependa da minha e vice-versa, para que um problema de entrega a um de nós não afete o outro.
4. Como irmão da usuária (novo destinatário), quero poder pedir `/frase` para receber uma frase extra, para ter a mesma experiência que a usuária já tem.
5. Como irmão da usuária, quero poder consultar `/status`, para saber se recebi a frase de hoje e diagnosticar problemas na minha própria entrega.
6. Como irmão da usuária, quero receber `/start` com a mesma ajuda que a usuária recebe, para entender como usar o bot sem precisar perguntar a ela.
7. Como usuária, quero que uma frase extra pedida pelo meu irmão seja só dele, para que `/frase` continue sendo uma solicitação pessoal e não dispare uma entrega para todo mundo.
8. Como usuária, quero que o sorteio sem repetição (ciclo) continue valendo para o conjunto compartilhado de frases entregues, para não regredir a garantia que já existe hoje de nunca repetir uma frase dentro do mesmo ciclo.
9. Como usuária, quero que uma frase já consumida por um pedido de vários destinatários seja contabilizada uma única vez no ciclo, para que ter dois destinatários não esgote a coleção duas vezes mais rápido.
10. Como usuária, quero que conversas fora do conjunto de destinatários continuem sendo recusadas silenciosamente, para manter o bot privado entre eu e as pessoas que eu autorizar.
11. Como usuária, quero cadastrar o chat_id do meu irmão como segredo, fora do Git e fora da conversa com o agente, para manter a mesma disciplina de segredos que o projeto já segue.
12. Como usuária, quero que adicionar um destinatário não exija mudança de permissão de infraestrutura (IAM), para manter o custo e a superfície de mudança pequenos.
13. Como desenvolvedora, quero que pedidos diários já existentes no formato antigo (um destinatário só) continuem legíveis como histórico, para não perder nem corromper dados já gravados na tabela `Retain`.
14. Como desenvolvedora, quero um teste que force deliberadamente a falha de entrega a um destinatário enquanto o outro recebe normalmente, para provar que as duas entregas são de fato independentes.
15. Como desenvolvedora, quero um teste que prove que a frase é consumida uma única vez no ciclo mesmo havendo múltiplos destinatários, para proteger a invariante de sorteio sem repetição.
16. Como usuária, quero que `/status` do meu irmão relate a entrega dele mesmo (recebeu/não recebeu/incerta), não um agregado que misture a minha situação com a dele.

## Implementation Decisions

- **Autorização (`dominio/autorizacao.py`):** `PoliticaDeAcesso.chat_id_autorizado: int` passa a ser um conjunto (`chat_ids_autorizados: frozenset[int]`). `conferir_conversa` passa a checar pertencimento ao conjunto em vez de igualdade. A ordem de verificação (segredo antes de conversa, `hmac.compare_digest`) não muda.
- **Pedido (`dominio/pedido.py`):** `Pedido.chat_id: int` passa a ser `Pedido.destinatarios: tuple[int, ...]` (não vazio). Um extra (`/frase`) sempre tem exatamente um destinatário — quem pediu. A diária carrega todos os destinatários autorizados no momento em que o pedido é criado.
- **Identidade da diária:** deixa de incluir o chat_id (`diaria#<chat_id>#<dia>` na v1) e passa a ser `diaria#<dia>` — um único pedido diário para todo o conjunto de destinatários, não um por pessoa. Identidades antigas no formato v1 permanecem como histórico, sem serem reprocessadas.
- **Reserva e consumo de frase (`dominio/ciclo.py`, `aplicacao/processar_pedido.py`):** continuam acontecendo uma única vez por pedido, independentemente de quantos destinatários ele tenha. Não há reserva nem consumo por destinatário — a garantia de "sorteio sem repetição" do ciclo é sobre pedidos, não sobre entregas individuais.
- **Entrega e rastreio de partes (`aplicacao/processar_pedido.py`, `persistencia/pedidos.py`):** a entrega passa a iterar destinatário × índice da parte. Cada combinação destinatário+parte confirma, fica incerta ou falha de forma independente das demais. O identificador de uma parte, hoje `pedido + índice`, passa a incorporar o destinatário.
- **Estado agregado do pedido:** o estado que controla retentativa e encerramento (`ENVIADO`/`PARCIAL`/`INCERTO`/`FALHOU`) reflete o pior caso entre destinatários — um pedido só é `ENVIADO` quando todos os destinatários confirmaram todas as partes. Uma falha permanente (ex.: bot bloqueado) para um destinatário não impede que os demais sejam tentados; o worker avança para os outros destinatários antes de decidir o desfecho do pedido.
- **`/status` (`dominio/status.py`, `aplicacao/consultar_status.py`):** a resposta a um destinatário é derivada da entrega **daquele destinatário** dentro do pedido do dia (partes confirmadas/incertas dele), não do estado agregado do pedido — para não relatar "parcial" a quem de fato recebeu tudo.
- **Extras (`/frase`):** sem mudança de desenho — a identidade já é por `bot + update_id` e o destinatário já vem da própria mensagem recebida. Autorizar um segundo chat_id nas políticas de acesso é suficiente para que `/frase` funcione para ele.
- **Compatibilidade de leitura:** um pedido persistido sem o campo `destinatarios` (formato anterior à v2) é lido como se `destinatarios = (chat_id_antigo,)` — mesmo padrão de compatibilidade que o projeto já usa para `bot_legado`/`estado_legado`.
- **Configuração e segredos (decidido):** o conjunto de destinatários autorizados é configurado em um único parâmetro novo no SSM Parameter Store, `telegram-chat-ids` (plural), sob o prefixo já existente `/frase-diaria/` — uma lista de chat_ids separados por vírgula (ex.: `<CHAT_ID_1>,<CHAT_ID_2>`), sem espaços exigidos mas tolerados na leitura. Esse parâmetro substitui o atual `telegram-chat-id` (singular), mas a migração é faseada entre dois tickets: o ticket 24 lê a lista inteira só para o conjunto de destinatários autorizados do webhook (`/frase`, `/status`, `/start`); o disparo agendado da diária continua lendo o `telegram-chat-id` singular até o ticket 25, que é quem migra `CriarDiaria` para múltiplos destinatários. Nenhuma mudança de política IAM é necessária — a permissão já cobre o prefixo inteiro. A usuária cadastra o valor pelo terminal dela, fora da conversa com o agente, seguindo a disciplina de segredos já documentada no projeto; o parâmetro antigo `telegram-chat-id` só é removido depois que o novo estiver confirmado em produção (ticket 27).
- **Sem limite numérico de destinatários (decidido):** o desenho não impõe um teto explícito de quantos chat_ids cabem na lista. Fica registrado como risco a observar, não como requisito: o tempo de fan-out do envio diário e o volume de escritas no DynamoDB crescem linearmente com o número de destinatários, e a janela de 08:00–08:15 (spec v1, 4.5) e a estimativa de custo (spec v1, 4.9) presumem um punhado de destinatários, não um número grande. Um crescimento muito além de "poucas pessoas da família" exigiria revisitar essa hipótese antes de ser seguro.
- **Sem mudança de infraestrutura além do(s) novo(s) parâmetro(s) SSM:** nenhum novo recurso AWS, sem VPC/NAT, sem mudança de custo recorrente relevante.

## Testing Decisions

- Fronteira principal continua sendo os casos de uso públicos (processar pedido, consultar status), com relógio, sorteio, Telegram e persistência controláveis — mesmo padrão da v1.
- Teste que **quebra a invariante de propósito** (convenção já usada no projeto, ver `rules.md`): dois destinatários num mesmo pedido diário, um `ErroDoTelegram` permanente simulado para um deles, e confirmar que (a) o outro destinatário recebe normalmente, (b) a frase é consumida uma única vez no ciclo, (c) nenhuma reserva fica órfã.
- Teste de autorização estendido (equivalente ao que hoje cobre um único chat_id): dois chat_ids autorizados aceitos, um chat_id desconhecido recusado, uma conversa de grupo recusada — cobrindo o mesmo critério que a v1 já verifica, agora para um conjunto.
- Teste de `/status` por destinatário: dois destinatários com desfechos diferentes na mesma diária (um confirmado, outro incerto) recebem respostas de `/status` diferentes, cada um refletindo só a própria entrega.
- Teste de compatibilidade: um pedido gravado no formato anterior (um único `chat_id`, sem `destinatarios`) continua sendo lido corretamente pelo código novo.
- Complementar com teste de concorrência do repositório de pedidos cobrindo a chave composta (pedido + destinatário + índice), no mesmo espírito dos testes de concorrência já existentes para o formato anterior.

## Out of Scope

- Destinatários dinâmicos ou autoinscrição (ex.: qualquer pessoa que mandar `/start` vira destinatário). O conjunto continua fixo e configurado pela usuária via segredo, não por interação no bot.
- Frases diferentes por destinatário no mesmo dia, ciclos independentes por pessoa, ou qualquer noção de "preferência" por destinatário.
- Múltiplos usuários no sentido amplo da spec v1 (grupos, canais públicos, quantidade arbitrária de pessoas). Esta spec abre exceção só para um conjunto pequeno e fixo de destinatários privados nomeados pela usuária — não remove a restrição geral contra grupos e canais públicos.
- Qualquer mudança em sincronização do Notion, formatação/limites de mensagem, janela de agendamento, publicação/CI-CD ou recuperação de versão — tudo isso permanece exatamente como a spec v1 descreve.
- Mensagens diferentes de ajuda (`/start`) por destinatário — todos recebem o mesmo texto de ajuda, salvo decisão em contrário.
- Migração retroativa de pedidos antigos para o novo formato — pedidos do formato v1 permanecem como estão, só não são mais produzidos.

## Further Notes

### Decisões fechadas no ticket 23

- **Mecanismo de configuração dos destinatários:** um único parâmetro SSM com lista (`telegram-chat-ids`, separados por vírgula) — ver "Implementation Decisions" acima. Não um parâmetro por destinatário.
- **Limite de destinatários:** sem teto numérico formal; registrado como risco a observar (custo e tempo de fan-out), não como requisito de validação.
- **Texto da seção "Fora de escopo" da spec v1:** atualizado (ver spec v1, seção 6) para restringir "múltiplos usuários" a um conjunto pequeno e fixo de destinatários privados nomeados pela usuária, mantendo grupos e canais públicos fora de escopo.
- **Numeração dos novos critérios de aceite:** AC32–AC37, adicionados à spec v1, seção 5.
- **Vocabulário:** "destinatário" e a redefinição plural de "conversa autorizada" foram incorporados à seção 2 da spec v1.

### Fora desta spec

- **Correção do `CLAUDE.md`:** a seção "Estado do repositório" do `CLAUDE.md` do projeto está desatualizada (registra só os tickets 01–06 como concluídos; na prática os 21 tickets originais já foram concluídos). Essa correção é independente desta spec v2 e não está coberta por ela.

### Sequenciamento sugerido (não vinculante)

O trabalho de implementação, quando aprovado, tende a se dividir em: (1) autorização multiautorizada; (2) núcleo da diária com múltiplos destinatários (reserva/consumo único, entrega em fan-out, rastreio por destinatário) — o maior e mais arriscado dos passos, por tocar as invariantes de concorrência do ciclo; (3) `/status` por destinatário; (4) verificação de que `/frase` já funciona para um segundo destinatário sem mudança adicional; (5) aceite real com o irmão como destinatário de fato.