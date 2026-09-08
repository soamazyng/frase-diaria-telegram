# /status completo

## Comportamento

`/status` passa a responder de verdade. Como `/frase`, o comando é registrado
no webhook (mesma autenticação: segredo + conversa autorizada) e despachado
ao worker de forma assíncrona — nada é montado nem enviado dentro da fronteira
HTTP. O worker lê o DynamoDB e envia um relatório em texto com:

- **Diária de hoje** — se ainda não foi criada, seu estado (pendente,
  enviando, aguardando nova tentativa, enviada, parcial, incerta, falhou,
  expirada) e o motivo, quando houver um relevante.
- **Último envio** — a diária de hoje, se já entregou algo, senão a de ontem;
  se nenhuma das duas entregou nada, "nunca". Partes incertas são sinalizadas
  explicitamente, com a nota de que não serão reenviadas automaticamente —
  tanto na diária de hoje quanto num último envio de outro dia.
- **Próxima ocorrência diária** — hoje às 08:00 local se a diária de hoje
  ainda não terminou; amanhã às 08:00 se já terminou.
- **Sincronização** — última tentativa (sucesso ou falha), última coleção
  válida e se veio do Notion ou do cache, e a falha ativa quando a última
  tentativa não teve sucesso.

Todos os horários aparecem em `America/Sao_Paulo` (AC17); nenhum instante cru
em UTC chega ao texto final.

## Decisão técnica

**Nova Lambda? Não — o mesmo worker, por payload.** `/status` é despachado à
mesma função `Worker` que já entrega frases, com um payload de formato
diferente (`{"status_chat_id": ...}` em vez de `{"pedido": ...}`).
`worker_handler.py` decide o caminho pela chave presente no evento. O worker
já tem toda a permissão necessária (leitura do DynamoDB); uma terceira Lambda
só para isto seria superfície de ataque sem benefício.

**`ConsultarStatus` não recebe `ciclos` nem `reserva`.** "Não consome frase
nem altera o ciclo" é garantido por construção — a classe simplesmente não
tem como chamar o que não recebeu — não por uma checagem em runtime que
alguém poderia esquecer de manter.

**Os dados de sincronização vêm de leitura persistida, não de uma
sincronização nova.** Esta foi a decisão que mudou depois do `/code-review`
(ver seção Review abaixo): a primeira versão desta sessão fazia `/status`
rodar `SincronizarColecao.executar()` ao vivo a cada consulta, reaproveitando
o resultado que ele já produz (`usou_cache`, `instante_do_snapshot`,
`erro_da_sincronizacao`). Isso tinha três problemas: chamava o Notion (e
podia regravar o snapshot) só por curiosidade da usuária; a "última falha"
que já tinha sido superada por uma nova tentativa bem-sucedida desaparecia
sem deixar rastro; e "última tentativa" sempre significava "agora", nunca
uma tentativa real do fluxo automático.

A correção: `SincronizarColecao.executar()` passou a registrar toda tentativa
— sucesso ou falha — num item separado do snapshot
(`RepositorioDeColecaoDynamo.registrar_tentativa`/`ultima_tentativa`, novo
domínio `TentativaDeSincronizacao`). `/status` só lê: `carregar_ativa()` para
a última coleção válida, `ultima_tentativa()` para a última tentativa e a
falha ativa. `usou_cache` é inferido comparando os dois — uma tentativa
recente com erro significa que o snapshot ativo não é fresco. `/status` não
tem mais nenhum caminho capaz de chamar o Notion.

**`Pedido.prazo`/`tentativa_unica` continuam só no domínio do envio; `/status`
não precisou de nada novo ali.** O que mudou no domínio do pedido foi só
`dia_alvo_da_diaria()` (extrai a data da própria identidade, sem campo novo
persistido — a identidade já a carrega) e a constante `MOTIVO_PADRAO`,
promovida de um literal duplicado para uma constante compartilhada entre
`dominio/pedido.py` e `telegram/status.py`.

**"Último envio" evita a palavra "confirmado".** Um envio parcial ou incerto
entra nesse campo (é o mais recente que chegou à usuária), mas "confirmado" é
vocabulário reservado a sucesso com confirmação persistida (`CLAUDE.md`). O
texto mostra o estado (enviada/parcial/incerta) para não perder a distinção
que o AC17 exige.

**"Último envio" alcança só hoje e ontem.** Não há índice por `chat_id` no
schema atual, e criar um só para isto seria escopo novo. Duas buscas
determinísticas (`identidade_de_diaria` de hoje e de ontem) bastam para o uso
real do comando; documentado explicitamente no código, não escondido atrás de
um nome genérico.

## Verificação

- Skills aplicadas: `implement`, `python-clean-code`, `tdd` e `code-review`.
- `ruff check`, `ruff format --check` e `mypy --strict`: OK.
- `sam validate --lint` no template de aplicação: OK, sem nenhuma mudança de
  IAM necessária (o worker já lia o DynamoDB inteiro; não precisa mais do
  segredo do Notion para `/status`, mas continua precisando dele para
  `ProcessarPedido`).
- `pytest`: 376 testes passaram. Novos: `dominio/tempo.proxima_ocorrencia_diaria`;
  `Pedido.dia_alvo_da_diaria`; `TentativaDeSincronizacao` e
  `registrar_tentativa`/`ultima_tentativa` em `persistencia/colecao.py`
  (round-trip via `moto`) e em `SincronizarColecao` (as três tentativas —
  sucesso, falha com cache, falha sem cache — registram a tentativa antes de
  retornar/propagar); `ConsultarStatus` (situação da diária, último envio,
  próxima ocorrência, sincronização lida do estado persistido, sem nenhum
  caminho para chamar sincronização de verdade); `formatar_status` (todas as
  distinções do AC17, fuso local, escape de HTML, rótulo "Último envio" sem
  "confirmado"); despacho de `/status` pelo webhook (autenticação, idempotência
  por `update_id`, falha do despacho não derruba o webhook).

## Review

Revisão em dois eixos (`/code-review`, agentes paralelos) sobre o diff antes
do commit — a mais consequente desta sessão até agora.

**Spec** — dois achados fortes, os dois corrigidos: (1) a implementação
original perdia a "última falha" assim que uma nova tentativa ao vivo (a
própria consulta) desse certo, e nunca mostrava uma tentativa real do fluxo
automático — resolvido com a leitura persistida descrita acima; (2)
"Última sincronização válida" simplesmente desaparecia do texto quando não
havia coleção disponível, em vez de dizer "nunca" como o campo irmão "Último
envio" já fazia — corrigido. Um achado classificado como implementação
questionável, corrigido: o rótulo "Último envio confirmado" incluía estados
parcial/incerto, contrariando o vocabulário do projeto. Um achado de scope
creep (a sincronização ao vivo a cada `/status`) deixou de existir com a
correção do primeiro achado, já que o redesenho eliminou a sincronização
disparada por `/status` por completo.

**Standards** — um achado real de duplicação corrigido: a constante local
`_MOTIVO_SEM_INTERESSE` duplicava o literal `"pedido criado"` de
`dominio/pedido.py`; promovida a `MOTIVO_PADRAO`, compartilhada pelos dois
módulos. Uma inconsistência de log corrigida (`_pedir_status` usava
`_log.error` onde o padrão do arquivo, em `_responder_ajuda`, é
`_log.exception`) — e a mesma inconsistência pré-existente em `_pedir_frase`
foi corrigida de passagem, já que era exatamente o padrão sendo restaurado.
Um comentário ausente adicionado (por que "último envio" alcança só dois
dias). Três achados foram registrados como julgamento e aceitos sem mudança,
com a razão do revisor concordada: o parâmetro booleano de
`proxima_ocorrencia_diaria` evita acoplar `dominio/tempo.py` a `dominio/pedido.py`;
o parsing reverso de `dia_alvo_da_diaria()` fica adjacente à construção da
identidade no mesmo arquivo; e os `Protocol`s locais de `consultar_status.py`
seguem a convenção já estabelecida no repositório (cada módulo declara o
próprio port mínimo).

## Próximo passo

Nenhum ticket bloqueado por 11 e 14 além deste permanece; o próximo elegível
por dependência é o **16 — Bootstrap OIDC e base do GitHub** (depende só do
ticket 01, concluído), início da Etapa 4 (CI/CD). A publicação real deste
ticket na AWS — exercitar `/status` contra o Telegram de verdade — fica para
quando a usuária autorizar uma nova publicação; nada foi publicado nesta
sessão.
