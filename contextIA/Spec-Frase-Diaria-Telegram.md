# Spec — Frase Diária no Telegram

Versão: 1.0  
Estado: refino funcional aprovado; implementação não iniciada.  
Triagem sugerida: ready-for-agent — indicação documental, sem label aplicada a um rastreador.  
Repositório previsto: frase-diaria-telegram, privado.  
Responsável pelo produto e merge: Jay.

## 1. Problema — Problem Statement

Minha coleção de frases está no Notion, mas depende de consulta manual para fazer parte da rotina. Quero receber esse conteúdo no Telegram e usar o projeto para praticar desenvolvimento de software com IA, com dedicação inferior a duas horas semanais.

O sinal de valor será identificar, após duas semanas de uso, pelo menos duas frases que provocaram reflexão ou ação. Essa avaliação é pessoal; não exige funcionalidade de feedback no bot.

### Fontes e precedência

1. O refino aprovado enviado nesta conversa determina o escopo.
2. O anexo Refino-inicial.txt complementa somente o que não conflita com o refino aprovado.
3. A [página original do projeto](https://app.notion.com/p/80a96c354e744bf192b73eb4224c6e9e) é referência histórica.
4. A [coleção no Notion](https://app.notion.com/p/260ec81f1f288005b4eee9fb3445364e) é a fonte de conteúdo do bot.

A versão consultada da coleção contém 77 itens numerados preenchidos, um item vazio e a subpágina do projeto. A aplicação deve descobrir o conteúdo a cada sincronização; esse número não é constante.

O refino aprovado substitui JSON local, SQLite, PostgreSQL, APScheduler e alternativas em TypeScript por sincronização com Notion, DynamoDB e serviços AWS. Docker e um servidor continuamente ligado não são requisitos. O comando /start do documento inicial será apenas uma ajuda de primeiro uso, sem envio de frase nem alteração do ciclo.

Os detalhes identificados como **proposta técnica** preenchem lacunas de implementação; não representam novas decisões funcionais já aprovadas.

## 2. Solução — Solution

Um bot pessoal envia uma frase diariamente às 8h, no fuso America/Sao_Paulo, inclusive em finais de semana. Antes de cada envio diário ou extra, consulta a coleção no Notion. Sorteia sem repetição até consumir a coleção e mantém histórico persistente.

A usuária pode pedir outra frase com /frase e consultar a operação com /status. Os envios independem do computador pessoal. A publicação acontece automaticamente a partir de dev, antes do merge manual para main, conforme a decisão expressa de operar um único ambiente de produção.

### Vocabulário

- **Frase:** item numerado preenchido e seu conteúdo associado.
- **Coleção válida:** snapshot completo e validado da fonte, inclusive um snapshot legitimamente vazio.
- **Ciclo:** conjunto de frases consumidas desde o último reinício da seleção.
- **Pedido de envio:** solicitação diária ou comando /frase, com identidade persistente.
- **Tentativa:** execução de um pedido; várias tentativas pertencem ao mesmo pedido.
- **Entrega confirmada:** Telegram retornou sucesso e a aplicação persistiu a confirmação.
- **Entrega incerta:** a chamada pode ter produzido mensagem, mas não há confirmação durável.
- **Versão estável:** publicação verificada e aceita por merge.
- **Versão candidata:** publicação de um PR ainda aberto.
- **Destinatário** (v2): uma conversa privada autorizada a receber entregas do bot. Até a v2 existia exatamente um; a partir da v2 existe um conjunto pequeno e fixo, configurado pela usuária. "Conversa autorizada", usado no restante desta spec, passa a significar "pertence ao conjunto de destinatários autorizados", não mais "é o único chat_id configurado". Ver `.scratch/v2-telegram-bot.md`.

## 3. Histórias de usuário — User Stories

1. Como usuária, quero receber uma frase diariamente às 8h, para incorporar reflexão à rotina.
2. Como usuária, quero o mesmo comportamento nos finais de semana, para manter a continuidade.
3. Como usuária, quero o fuso de São Paulo, para receber no horário local correto.
4. Como usuária, quero que o bot funcione com meu computador desligado, para dispensar execução manual.
5. Como usuária, quero usar a coleção do Notion diretamente, para manter uma única fonte de conteúdo.
6. Como usuária, quero ignorar itens vazios e a subpágina do projeto, para receber apenas frases.
7. Como usuária, quero preservar autoria, origem, comentários, tags e links, para manter o contexto.
8. Como usuária, quero destaques adaptados ao Telegram, para conservar a intenção visual.
9. Como usuária, quero manter as autorias cadastradas, para preservar minha coleção.
10. Como usuária, quero receber somente conteúdo existente, para evitar frases ou comentários gerados por IA.
11. Como usuária, quero que novas frases entrem no ciclo atual, para começar a recebê-las sem reiniciar a coleção.
12. Como usuária, quero que edições mantenham a identidade da frase, para evitar repetição indevida.
13. Como usuária, quero retirar frases excluídas das próximas seleções, para respeitar minhas mudanças.
14. Como usuária, quero preservar envios antigos após edições e exclusões, para consultar o que ocorreu.
15. Como usuária, quero usar a última coleção válida quando o Notion falhar, para continuar recebendo frases.
16. Como usuária, quero que a falta de uma coleção válida seja registrada, para identificar a causa da ausência de envio.
17. Como usuária, quero um sorteio sem repetição no ciclo, para percorrer toda a coleção.
18. Como usuária, quero um novo ciclo aleatório ao terminar a coleção, para continuar recebendo conteúdo.
19. Como usuária, quero evitar repetição na transição entre ciclos quando houver alternativa, para variar as mensagens.
20. Como usuária, quero pedir /frase, para receber uma frase extra.
21. Como usuária, quero que extras e diárias compartilhem o ciclo, para manter a regra de repetição.
22. Como usuária, quero que uma frase extra preserve o envio diário, para manter a rotina agendada.
23. Como usuária, quero consultar último envio e próximo horário com /status, para acompanhar a operação.
24. Como usuária, quero consultar sincronização e falhas com /status, para diagnosticar problemas.
25. Como usuária, quero novas tentativas até o meio-dia, para recuperar falhas temporárias.
26. Como usuária, quero abandonar a diária atrasada após o limite, para evitar acúmulo.
27. Como usuária, quero histórico persistente de resultados e tentativas, para manter rastreabilidade após reinícios.
28. Como usuária, quero controlar execuções duplicadas e concorrentes, para reduzir mensagens repetidas.
29. Como usuária, quero acesso limitado à minha conversa privada, para manter o bot pessoal.
30. Como desenvolvedora, quero implementar por etapas com explicações, para aprender dentro do tempo disponível.
31. Como desenvolvedora, quero infraestrutura declarada em SAM, para reproduzir o ambiente.
32. Como desenvolvedora, quero OIDC e credenciais temporárias, para publicar sem chaves AWS permanentes no GitHub.
33. Como desenvolvedora, quero um PR automático de dev para main, para reduzir tarefas repetitivas.
34. Como desenvolvedora, quero atualizar o mesmo PR a cada push, para concentrar a revisão.
35. Como desenvolvedora, quero testes e validações vinculados ao commit, para saber exatamente o que foi avaliado.
36. Como desenvolvedora, quero publicar o commit do PR antes do merge, para verificar a publicação real.
37. Como desenvolvedora, quero publicações sequenciais, para evitar concorrência sobre produção.
38. Como desenvolvedora, quero o merge bloqueado em caso de falha, para manter o fluxo aprovado.
39. Como desenvolvedora, quero decidir o merge manualmente, para controlar a aceitação da versão.
40. Como desenvolvedora, quero restaurar a versão anterior após falhas ou abandono do PR, para recuperar o serviço.
41. Como desenvolvedora, quero preservar dados e histórico na recuperação, para manter a continuidade.
42. Como desenvolvedora, quero acompanhar consumo AWS e GitHub Actions, para perseguir a meta de custo recorrente zero.

## 4. Decisões de implementação — Implementation Decisions

### 4.1 Arquitetura e responsabilidades

Stack aprovada: Python, FastAPI, Mangum, AWS SAM, Lambda, EventBridge Scheduler, DynamoDB e GitHub Actions.

Proposta técnica: uma aplicação Python com entradas separadas para HTTP e trabalho agendado. FastAPI recebe o webhook via API Gateway HTTP API; Mangum adapta os eventos. O agendamento chama diretamente os casos de uso Python. Um worker processa pedidos persistidos, sem depender de tarefas em segundo plano após retornar a resposta HTTP.

Responsabilidades dos módulos:

- Domínio: seleção, ciclos, elegibilidade, janela de envio e estados de entrega.
- Aplicação: coordenar sincronização, reserva, tentativa, confirmação e status.
- Notion: buscar blocos e converter conteúdo em uma representação preservável.
- Telegram: validar entrada e enviar partes de texto.
- Persistência: snapshots, ciclos, pedidos, tentativas e controle de concorrência.
- Infraestrutura: recursos, permissões, agendamento, entrada HTTP e retenção.
- Publicação: PR, verificações, artefatos, promoção e recuperação.

Relógio, gerador aleatório e integrações devem ser substituíveis nos testes. Manter os casos de uso independentes de FastAPI e dos formatos de evento AWS.

### 4.2 Leitura e sincronização do Notion

A integração de produção deverá ter acesso de leitura à página. O acesso obtido nesta conversa não configura as credenciais da futura aplicação.

Selecionar itens numerados preenchidos do nível da coleção. O conteúdo descendente pertence à frase que o contém; uma lista numerada interna não cria frases independentes. Ignorar blocos de subpágina e o projeto inteiro. Conteúdo solto cuja associação seja ambígua deve gerar diagnóstico, sem atribuição inventada.

Usar o identificador do bloco raiz como identidade estável, internamente. Mover ou editar o mesmo bloco mantém a identidade. Apagar e recriar um bloco cria outra identidade; igualdade de texto não é critério automático de deduplicação.

Preservar conteúdo em ordem, com rich text e vínculos associados. Evitar separar autoria por heurísticas frágeis: quando texto e autoria estiverem misturados, conservar o conteúdo literal. Comentários pessoais no corpo entram na frase; para discussões nativas associadas ao bloco, validar acesso e recuperar quando disponíveis. Uma limitação de acesso deve aparecer no diagnóstico, nunca como extração completa.

Percorrer toda a paginação e os descendentes relevantes. Publicar um novo snapshot somente após concluir e validar a leitura. Uma resposta parcial, erro de autorização ou timeout não pode ser interpretado como exclusão em massa. A API exige paginação e leitura adicional de filhos para representar todo o conteúdo. [Documentação do Notion](https://developers.notion.com/reference/get-block-children)

Uma leitura completa sem frases substitui a coleção por um snapshot vazio: registrar “coleção vazia” e não ressuscitar itens excluídos. Na indisponibilidade, manter a última versão válida e indicar uso de cache, data e erro da sincronização.

Sincronizar antes de cada pedido diário ou extra e novamente antes de uma nova tentativa que vá enviar conteúdo. Para uma tentativa sem nenhuma parte enviada, atualizar o conteúdo da frase reservada; se excluída, liberar e selecionar outra elegível. Após uma entrega parcial, manter a versão iniciada para concluir as partes restantes, registrando eventual alteração da fonte.

### 4.3 Formatação e limites

Proposta técnica: renderização em HTML suportado pela Bot API, com escape de caracteres e preservação de negrito, itálico, código e links. Cores e fundos do Notion tornam-se destaque em negrito quando não houver equivalente. Remover apenas metadados operacionais da mensagem.

Uma frase é uma entrega lógica e pode ocupar várias mensagens. Dividir texto sem perda, mantendo a ordem e marcação válida. A implementação deve validar limites de texto pelos contratos atuais da [Telegram Bot API](https://core.telegram.org/bots/api).

Salvar todas as partes e suas confirmações.

### 4.4 Seleção e ciclos

Obter frases ativas que ainda não tenham sido consumidas nem estejam reservadas no ciclo. Sortear entre as elegíveis. Novas identidades entram imediatamente; edições não apagam a marca de consumo. Exclusões removem a elegibilidade, preservando o histórico.

Abrir outro ciclo quando todas as frases ativas tiverem sido consumidas e não houver reservas pendentes. Com pelo menos duas frases ativas, excluir a última entregue das candidatas à primeira seleção do novo ciclo. Com apenas uma, a repetição é inevitável e permitida; com zero, registrar ausência de conteúdo.

Diárias e extras utilizam o mesmo estado de ciclo. Uma nova tentativa reutiliza a reserva existente e não sorteia outra frase arbitrariamente.

Consumo normal ocorre após entrega completa confirmada. Uma falha comprovada sem envio libera a reserva ao encerrar o pedido. Entrega parcial ou incerta mantém a frase marcada como utilizada com ressalva naquele ciclo, para evitar reinício automático de algo que já pode ter chegado.

### 4.5 Agendamento, fila persistente e novas tentativas

Envio-alvo às 08:00 em America/Sao_Paulo; operação normal entre 08:00 e 08:15. A janela de recuperação termina às 12:00 do mesmo dia local. Salvar instantes em UTC e calcular a chave diária pelo dia local.

Proposta técnica: Scheduler diário cria o pedido; um segundo disparo periódico, a cada cinco minutos, recupera pedidos pendentes e execuções interrompidas. O reconciliador pode criar a diária ausente durante a janela, cobrindo falha do disparo principal. A chave diária torna as duas entradas idempotentes.

Persistir o próximo instante de tentativa; não manter Lambda dormindo. Usar espera progressiva limitada, com dispersão e respeito ao retry_after quando informado. Checar a janela imediatamente antes de cada chamada ao Telegram. Às 12:00, encerrar a diária pendente, inclusive parcial, e conservar o resultado. No dia seguinte criar somente o pedido do novo dia.

Erros transitórios permitem retentativa; erros permanentes, como credencial inválida ou bot bloqueado, encerram o pedido com diagnóstico. Após correção, um novo comando pode ser processado; uma diária ainda na janela pode ser retomada operacionalmente sem duplicar a identidade.

Proposta técnica para a lacuna dos extras: /frase funciona a qualquer hora. Extras recebidas antes de 12:00 podem tentar novamente até 12:00; extras a partir de 12:00 têm uma tentativa imediata, sem fila para o dia seguinte. Essa política precisa de validação da usuária antes de fechar o comportamento de falhas dos extras.

### 4.6 Idempotência e limite de entrega exatamente uma vez

Identidades de pedido:

- Diária: conversa autorizada + data local.
- Extra: bot + update_id do Telegram.
- Parte: pedido + índice da parte.
- Tentativa: pedido + número sequencial.

Usar escritas condicionais e transações para reservar pedido e frase. Proteger o estado do ciclo e a sequência de envio com lease de duração limitada e token de versão, impedindo que um executor antigo confirme ou avance uma reserva já transferida. Uma execução interrompida deve ser reconciliável sem bloqueio permanente.

O banco e a chamada externa ao Telegram não participam da mesma transação. Timeout após aceitação, ou interrupção antes de persistir a resposta, pode deixar a entrega incerta. A spec não promete exatamente uma mensagem sob todas as falhas de rede.

Proposta técnica: registrar intenção por parte antes do envio; diante de resultado ambíguo, marcar entrega incerta e suspender reenvio automático dessa parte. Expor a situação em /status. Se houver sucesso externo conhecido mas persistência temporariamente indisponível, tentar persistir a confirmação sem reenviar. Essa escolha reduz duplicação, com risco explícito de uma entrega perdida; precisa ser validada antes da implementação da confiabilidade.

### 4.7 Contratos do Telegram e HTTP

- POST /telegram/webhook: recebe Update, valida segredo do webhook, conversa privada e chat_id autorizado; persiste o comando antes de confirmar recebimento.
- GET /health: retorna saúde básica e identificador da versão, sem dados pessoais ou segredos.
- /frase: cria pedido extra e tenta acordar o worker; o reconciliador cobre falha desse acionamento.
- /status: responde com último envio confirmado, próxima ocorrência diária, situação da diária atual, última sincronização válida, última tentativa de sincronização, uso de cache e falhas ativas ou última falha.
- /start: informa /frase e /status; não consome frase.
- Comando desconhecido autorizado: responde ajuda curta.
- Conversa não autorizada: não envia resposta nem conteúdo e não cria pedido.

Webhook repetido retorna sucesso após reconhecer o registro existente. Falha ao persistir retorna erro para permitir nova entrega pelo Telegram. Atualizações irrelevantes já validadas podem ser reconhecidas e ignoradas.

Validar o cabeçalho X-Telegram-Bot-Api-Secret-Token e conferir o tipo private e o chat_id configurado. /status também passa pela autenticação. O protocolo de webhook e seu segredo estão descritos na [Telegram Bot API](https://core.telegram.org/bots/api#setwebhook).

### 4.8 Persistência e observabilidade

DynamoDB será a fonte persistente do estado operacional. Proposta de entidades lógicas, sem impor caminhos ou nomes físicos:

- Frase: identidade, versão do conteúdo, estado ativo e representação rica.
- Snapshot: identificador, instante, resultado de validação, quantidade e referência ao snapshot ativo.
- Ciclo: identificador, versão concorrente, última frase entregue e estado de consumo por identidade.
- Pedido: origem, chave idempotente, data-alvo, prazo, estado, reserva, conteúdo usado e próximo processamento.
- Parte: posição, tipo, estado, intenção de envio, confirmação e message_id.
- Tentativa: instante, resultado, erro sanitizado, versão da aplicação e correlação.
- Sincronização: última tentativa, último sucesso, falha e uso de cache.
- Publicação: PR, SHA, artefato, estado, versão anterior e versão estável.

Distribuir conteúdo extenso e históricos em itens separados; não depender de um único item com crescimento ilimitado. Índice de pendências deve permitir buscar trabalho vencido sem varrer o histórico.

Estados de pedido: pendente, reservado, enviando, aguardando tentativa, enviado, parcial, incerto, falhou e expirado. Transições devem guardar os motivos; estados terminais não são reabertos por evento duplicado.

Preservar o conteúdo efetivamente enviado no histórico, mesmo se a origem mudar. Dados e histórico não expiram automaticamente. Logs técnicos podem ter retenção limitada, proposta inicial de 14 dias; não substituem o histórico.

Registrar atrasos acima de 15 minutos, falhas de integração, lock expirado, pedidos incertos e recuperação de publicação. O sucesso significa aceitação pela API, não leitura pela usuária. Remover tokens, URLs assinadas e conteúdo pessoal desnecessário dos logs.

### 4.9 Infraestrutura, segredos e orçamento

SAM declara Lambda, Scheduler, DynamoDB e, na proposta técnica, HTTP API, logs e permissões IAM. Selecionar runtime Python suportado no momento da implementação e fixar dependências testadas.

Separar recursos duráveis de dados dos recursos de aplicação para que atualizações e recuperação não apaguem histórico. Aplicar retenção e proteção contra exclusão dos recursos persistentes. Usar permissões específicas por função e criptografia dos serviços.

Configurações mínimas: página do Notion, token da integração, token do Telegram, conversa autorizada, segredo do webhook, horário, fuso, janela de recuperação e identificadores dos recursos. Valores sensíveis são cadastrados fora do Git; parâmetros de infraestrutura não devem aparecer em logs. Escolher o armazenamento de segredos após verificar custo, acesso e rotação.

Meta recorrente R$0, sem promessa de gratuidade. Antes do provisionamento, verificar elegibilidade da conta AWS, região, franquias e recursos auxiliares: API Gateway, logs, DynamoDB e índices, segredos/KMS, Scheduler, Lambda, tráfego e artefatos. Evitar VPC/NAT sem necessidade demonstrada. Registrar estimativa datada e como consultar consumo.

No GitHub, verificar plano, minutos, armazenamento de artefatos e permissões. O desenho com varredura a cada cinco minutos também precisa entrar na estimativa. Nenhuma chamada paga de IA faz parte da operação do bot.

### 4.10 Bootstrap AWS e GitHub

Repositório privado com dev e main permanentes, único ambiente de produção. O estado informado é de projeto não iniciado; nenhum código existente, ADR ou convenção de testes foi apresentado.

A confiança OIDC precisa existir antes do primeiro pipeline com acesso AWS. Entregar configuração declarativa de bootstrap e instrução de execução única com uma identidade AWS já autorizada. Um pipeline ainda sem confiança não pode criar sua própria autorização inicial.

Restringir confiança a proprietário/repositório e contexto de execução autorizado; validar audience e subject. Conceder id-token: write somente ao trabalho que precisa assumir papel AWS. Separar papel de publicação e papel de execução da infraestrutura, com escopo controlado.

Inicializar main com o necessário para os workflows e configuração do repositório; criar dev a partir dela. Essa base inicial não precisa publicar uma versão do bot. Validar as políticas efetivas do GitHub e a permissão para Actions criar PRs.

### 4.11 PR automático, publicação e merge

O gatilho principal é push remoto para dev. Havendo diferenças para main, criar PR dev → main se não existir; caso exista, continuar no mesmo PR. Push sem diferenças não cria PR. O merge é manual e dev deve permanecer existente.

Proposta técnica: encadear criação/localização de PR e CI/CD no próprio workflow de push ou por workflow reutilizável. Não depender exclusivamente de um evento pull_request produzido pelo GITHUB_TOKEN: há regras próprias de disparo e aprovação desses eventos. [Eventos do GitHub Actions](https://docs.github.com/actions/using-workflows/events-that-trigger-workflows)

Fluxo obrigatório:

1. Capturar SHA imutável do push e localizar o PR correspondente.
2. Executar testes, análise estática e validação SAM.
3. Construir uma vez e identificar o artefato pelo SHA e checksum.
4. Entrar na exclusão mútua de produção; reconsultar PR aberto e SHA atual.
5. Registrar publicação em andamento e invalidar a elegibilidade de merge da candidata anterior.
6. Publicar exatamente o artefato avaliado.
7. Verificar saúde, versão ativa, acesso às dependências e configuração do webhook/agendamento.
8. Registrar sucesso somente no SHA efetivamente publicado e ainda atual no PR.
9. Permitir merge manual com as verificações obrigatórias aprovadas.

Um novo push exige nova avaliação. Apenas trabalhos sem mutação podem ser cancelados livremente. Publicação e recuperação compartilham o mesmo grupo de exclusão mútua, com verificação de atualidade após esperar; não presumir ordem FIFO dos jobs.

A verificação pós-publicação usa consultas e diagnóstico sem consumir frase nem enviar mensagem de teste a cada commit. O teste real de entrega fica no aceite inicial controlado. Uma indisponibilidade detectada no diagnóstico pode reprovar a publicação e disparar recuperação.

Proteger main contra push direto e exigir o conjunto de checks, incluindo publicação validada. Desabilitar caminhos de bypass quando aplicável. A exigência automática em repositório privado depende de plano compatível; GitHub documenta suporte em Pro, Team e Enterprise. Verificar a conta antes de declarar esse requisito concluído. [Proteção de branches](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches)

Proposta técnica: merge commit preservando o histórico de dev; desabilitar exclusão automática de dev. Antes de publicar, exigir que o conteúdo de dev inclua a base relevante de main. Após merge, registrar qual SHA testado foi incorporado, validar equivalência de conteúdo e marcar a versão como estável. O evento de merge não refaz a publicação.

Durante o PR aberto, produção pode estar à frente de main. A verificação de merge deve corresponder ao código atualmente implantado; uma recuperação invalida esse resultado mesmo que o SHA já tenha passado anteriormente.

### 4.12 Recuperação da versão anterior

Preservar artefatos imutáveis, configuração e manifesto suficientes para restaurar uma publicação sem reconstruir dependências. Manter dois marcos: publicação saudável anterior à tentativa e versão estável aceita em main.

- Falha de deploy: recuperar a publicação saudável anterior à tentativa, verificando também rollback nativo da infraestrutura.
- Falha do diagnóstico: recuperar a publicação saudável anterior à tentativa.
- Fechamento de PR sem merge: recuperar a versão estável anterior ao PR, e não uma candidata anterior do mesmo PR.
- Primeiro deploy sem versão anterior: reverter os recursos de aplicação possíveis e deixar envios desabilitados; preservar dados já criados e registrar ausência de versão recuperável.

Antes de recuperar, conferir se a publicação ativa ainda pertence à tentativa ou PR afetado. Um evento antigo não pode sobrescrever uma publicação posterior. Repetir o evento de recuperação deve ser idempotente.

Restaurar código, configurações e pontos de entrada compatíveis. Mudanças de dados serão aditivas e legíveis pela versão anterior; migrações destrutivas não entram no MVP. O histórico não volta no tempo e mensagens enviadas permanecem no Telegram.

Verificar a versão restaurada e guardar o resultado. Se a recuperação falhar, manter merge bloqueado, registrar diagnóstico no GitHub e disponibilizar procedimento manual com o último artefato válido. Desabilitar novos envios quando não houver versão operacional verificável.

Um reconciliador de publicações deve cobrir interrupção do runner e falha do evento de fechamento do PR. Proposta: workflow periódico consulta o manifesto de publicação e o estado do PR, adquirindo a mesma exclusão mútua antes de agir. Essa execução também entra na estimativa do Actions.

## 5. Decisões de testes — Testing Decisions

### Fronteira principal

Proposta: concentrar os testes de negócio nos casos de uso públicos de enviar frase e consultar status, com relógio, sorteio, Notion, Telegram e persistência controláveis. Verificar mensagens produzidas, estado observável e histórico, evitando testar métodos privados ou espelhar a implementação.

Complementar com testes de contrato nas fronteiras HTTP e de integração, e testes de concorrência do repositório DynamoDB. Não há testes anteriores apresentados para reutilizar. A validação dessa fronteira pela usuária é a checagem solicitada pela skill To Spec; não impede a entrega desta spec.

### Critérios de aceite verificáveis

- AC01 — Relógio local entre 08:00 e 08:15 em um dia normal produz uma diária; finais de semana seguem a mesma regra.
- AC02 — Repetir evento diário, webhook ou recuperação de worker mantém a mesma identidade de pedido.
- AC03 — Dois workers concorrentes não reservam a mesma frase nem avançam o ciclo de modo inconsistente.
- AC04 — Com coleção estável de N frases, N entregas no ciclo têm identidades distintas.
- AC05 — Com duas ou mais frases, a primeira do novo ciclo difere da última anterior; com uma, repete; com zero, informa ausência.
- AC06 — /frase usa o ciclo comum e não satisfaz nem cancela a diária.
- AC07 — Inserção entra no ciclo; edição mantém identidade e consumo; exclusão remove elegibilidade.
- AC08 — Leitura paginada incompleta conserva o snapshot anterior e não gera exclusões.
- AC09 — Notion indisponível utiliza cache válido; sem cache registra falha; coleção legitimamente vazia não usa frases antigas.
- AC10 — Parser preserva conteúdo e autoria literalmente, ignora item vazio/subpágina e mantém associação de filhos.
- AC11 — Texto longo, acentos, caracteres especiais, links e destaques mantêm conteúdo e ordem na renderização.
- AC13 — Falha transitória agenda tentativa do mesmo pedido; falha permanente encerra sem repetição infinita.
- AC14 — Às 12:00 nenhuma nova chamada da diária é iniciada; diária vencida não reaparece no dia seguinte.
- AC15 — Reinício após reserva, após envio e durante confirmação não perde histórico; intenção sem confirmação resulta em estado incerto.
- AC16 — Entrega parcial retoma somente partes comprovadamente pendentes; partes incertas não são reenviadas automaticamente.
- AC17 — /status distingue nunca enviado, cache desatualizado, falha, parcial e incerto, com horários locais.
- AC18 — Conversa de grupo, chat_id diferente e segredo inválido não produzem frases nem pedidos autorizados.
- AC19 — Primeiro push com diferenças abre um PR; pushes seguintes mantêm o PR; push após merge abre outro quando houver diferenças.
- AC20 — Teste, análise ou validação SAM falhos impedem publicação e deixam o merge bloqueado.
- AC21 — O SHA testado, artefato publicado, versão ativa e check de merge correspondem entre si.
- AC22 — Push durante publicação não permite que o resultado antigo aprove o novo commit.
- AC23 — Deploys, rollback e fechamento de PR concorrentes não sobrescrevem uma versão mais recente por evento obsoleto.
- AC24 — Falha de publicação ou diagnóstico restaura a versão anterior verificável; primeira publicação falha tem estado documentado.
- AC25 — Fechar PR abandonado após várias candidatas restaura a versão estável anterior ao PR.
- AC26 — Atualização e recuperação preservam histórico e compatibilidade dos dados.
- AC27 — Merge manual de candidata saudável apenas a registra como estável; não dispara segunda publicação.
- AC28 — Papel OIDC aceita somente o contexto autorizado; segredos não aparecem no Git ou nos logs.
- AC29 — A proteção de main é exercitada no repositório real e impede merge com checks falhos ou ausentes.
- AC30 — Documentação de operação permite configurar credenciais, diagnosticar falha e executar recuperação.
- AC31 — Duas semanas de uso permitem a avaliação pessoal das duas frases de valor, sem exigir coleta automática.

Critérios a seguir cobrem múltiplos destinatários (v2, `.scratch/v2-telegram-bot.md`):

- AC32 — Com múltiplos destinatários configurados, uma mesma diária entrega texto idêntico, vindo de um único sorteio, a todos eles.
- AC33 — Falha permanente de entrega a um destinatário não impede, atrasa nem encerra a entrega aos demais destinatários do mesmo pedido.
- AC34 — Uma frase entregue a vários destinatários no mesmo pedido é consumida uma única vez no ciclo, nunca uma vez por destinatário.
- AC35 — `/status` de cada destinatário reflete a entrega dele mesmo (confirmada, incerta, parcial ou falha), independentemente do resultado dos demais destinatários no mesmo pedido.
- AC36 — Um destinatário autorizado adicional usa `/frase` e `/status` com o mesmo comportamento e autenticação que o destinatário original.
- AC37 — Um chat_id fora do conjunto configurado de destinatários continua sem resposta e sem pedido, independentemente de quantos destinatários existam.

A suíte de CI usa fixtures e integrações simuladas para resultados reproduzíveis. Testes específicos de persistência validam atomicidade, retomada e concorrência. O aceite AWS inclui uma entrega real autorizada, /frase, /status, persistência entre versões e exercício controlado de recuperação. Não criar um ambiente permanente de dev.

## 6. Fora do escopo — Out of Scope

- Múltiplos usuários além de um conjunto pequeno e fixo de destinatários privados, nomeados pela usuária (v2, `.scratch/v2-telegram-bot.md`); grupos e canais públicos continuam fora de escopo, assim como destinatários dinâmicos ou autoinscrição por interação no bot.
- Interface administrativa, dashboard web e aplicativo próprio.
- IA para gerar, comentar, corrigir autoria ou recomendar frases durante a operação.
- Filtros por tema, favoritas, avaliações, resumos semanais ou horários por dia.
- Cards gerados e edição artística das imagens.
- Preservação, cache ou envio de imagens da coleção do Notion; frases usam apenas texto.
- Fonte local JSON, SQLite ou PostgreSQL como armazenamento de produção.
- Ambiente AWS permanente para dev.
- Merge automático ou publicação apenas após merge.
- Exclusão de mensagens enviadas durante recuperação.
- Garantia de entrega exatamente uma vez em falhas externas ambíguas.
- Implementação do código nesta etapa de especificação.

## 7. Notas adicionais — Further Notes

### Plano de implementação

**Etapa 1 — Base e testes.** Criar domínio e casos de uso; implementar seleção, ciclos e identidades de pedido; usar dependências simuladas. Concluir com AC04–AC07 e testes de janela e duplicidade reproduzíveis. Não provisionar AWS.

**Etapa 2 — Integrações.** Implementar leitura Notion, renderização Telegram, comandos e modelo persistente. Concluir com contratos verificáveis, preservação do conteúdo, autenticação e sincronização parcial cobertas. Usar fixtures locais antes do aceite real.

**Etapa 3 — Infraestrutura.** Declarar recursos em SAM, agendamento, worker/reconciliador, segredos, retenção e tentativas. Concluir com uma entrega real, persistência após reinício, diagnóstico de falhas e estimativa de consumo.

**Etapa 4 — CI/CD.** Executar bootstrap OIDC, automatizar PR, validar commit, serializar publicação, bloquear merge e exercitar recuperação. Concluir com AC19–AC30 demonstrados, inclusive PR abandonado e falha inicial.

Dividir o trabalho em sessões pequenas compatíveis com menos de duas horas semanais. Cada entrega deve explicar o comportamento implementado, a decisão técnica, o que os testes demonstram e o próximo passo. Essa disponibilidade não implica promessa de prazo total.

### Dependências e condições de desbloqueio

- Conta/plano e permissão GitHub: verificar antes da etapa 4; se não permitir bloqueio de merge privado, apresentar a incompatibilidade. Não tornar o repositório público nem relaxar a exigência automaticamente.
- AWS: confirmar conta, região, identidade para bootstrap e elegibilidade das franquias antes de provisionar.
- Notion: fornecer credencial de integração e compartilhar a página com ela antes do teste real da etapa 2.
- Telegram: criar bot, iniciar conversa privada e cadastrar token, chat_id e segredo fora do repositório.
- Fronteira de testes: proposta registrada na seção 5 para revisão.
- Políticas complementares: validar a janela de retentativa de extras e o tratamento conservador de entrega incerta antes da etapa 3.
- Recursos auxiliares: validar HTTP API e armazenamento de segredos na estimativa de infraestrutura; são escolhas propostas, não serviços previamente aprovados no refino.
- Issue tracker: não foi informado um rastreador nem seu vocabulário. A skill To Spec orienta executar /setup-matt-pocock-skills para configurá-los. Até isso ocorrer, esta spec fica na página do projeto no Notion e em Markdown; ready-for-agent é apenas triagem sugerida.

### Definição de pronto

MVP concluído quando os critérios técnicos aplicáveis estiverem verificados, as dependências resolvidas, o envio diário e os comandos estiverem operacionais, o histórico sobreviver às publicações e a recuperação estiver exercitada. Registrar limitações remanescentes explicitamente. A avaliação pessoal após duas semanas completa a validação de valor.

