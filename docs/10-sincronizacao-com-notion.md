# Sincronização com Notion substitui as fixtures

**Ticket:** 10 — Sincronização com Notion substitui as fixtures

## Objetivo

Ler a coleção do Notion e produzir um snapshot completo e validado (`ColecaoValida`, vocabulário da spec) — sem inventar atribuição, sem confundir descendente com frase independente, e sem nunca interpretar uma leitura parcial como exclusão em massa.

## Escopo desta sessão

Este ticket entrega o **núcleo de leitura e conversão** — ler, decidir o que é frase, preservar o conteúdo, diagnosticar o ambíguo. Ele **não** inclui:

- persistência durável do snapshot e cache de indisponibilidade (ticket 11);
- renderização em HTML do Telegram e divisão de mensagens (ticket 12);
- a credencial de produção cadastrada no SSM e o `page_id` real da coleção (passo manual da usuária, fora do repositório).

Por isso `Frase` (`dominio/frase.py`, consumida por `ProcessarPedido`) não muda: ela continua sendo a representação **pronta para envio**, que `ColecaoFixture` fornece até o ticket 12 existir para convertê-la a partir da `ColecaoValida` preservada aqui.

## O que foi construído

**Domínio puro** (`dominio/conteudo.py`, `dominio/colecao.py`):

- `Trecho` — um segmento de rich text, com anotações (negrito, itálico, tachado, sublinhado, código) e link, preservados literalmente.
- `Bloco` — um bloco de conteúdo na ordem em que aparece, com o tipo bruto da fonte.
- `FrasePreservada` — identidade (id do bloco raiz) + blocos + discussões nativas.
- `ColecaoValida` — o snapshot: itens e diagnósticos. Uma coleção vazia é um valor legítimo.
- `SincronizacaoIncompleta` — exceção distinta para leitura parcial, erro de autorização ou timeout; nunca um `ColecaoValida` truncado.

**Cliente HTTP do Notion** (`notion/cliente.py`): `urllib` da biblioteca padrão, como `telegram/canal.py` — evita uma dependência a mais no artefato da Lambda. Paginação resolvida internamente (quem chama recebe tudo ou uma exceção, nunca uma lista truncada). Rate limit (429) espera e tenta de novo, honrando `Retry-After`. Acesso negado (403) vira `AcessoNegado`, distinguível para o caso especial de comentários.

**Leitor da coleção** (`notion/leitura.py`): percorre o nível da coleção, aplica as regras:

- só item numerado **preenchido** vira frase (item vazio é ignorado, não é diagnóstico — AC10);
- subpágina — inclusive a do projeto inteiro — é ignorada;
- qualquer outro tipo solto no nível da coleção vira diagnóstico `conteudo_solto`;
- descendentes (inclusive uma lista numerada aninhada) entram como blocos da mesma frase, nunca como frase independente;
- discussões nativas são buscadas por frase; acesso negado vira diagnóstico `acesso_negado`, sem invalidar a coleção inteira;
- qualquer erro do Notion, no nível da coleção ou nos descendentes, vira `SincronizacaoIncompleta` — nunca uma coleção com menos itens.

## Onde a política fica

- `src/frase_diaria/dominio/conteudo.py` e `dominio/colecao.py` — o modelo.
- `src/frase_diaria/notion/cliente.py` — HTTP, paginação, autenticação, erros sanitizados.
- `src/frase_diaria/notion/leitura.py` — a decisão de o que é frase, descendente ou ruído.

## Achados do code-review corrigidos

A primeira rodada de `/code-review` não viu estes arquivos — eram *untracked*
e não apareciam no diff. Depois de dar `git add` neles, uma segunda rodada
encontrou e confirmou dois defeitos, ambos corrigidos antes do commit:

- `_ler_discussoes` não capturava `ErroDoNotion`: um erro do Notion ao buscar
  discussões que não fosse 403 (rede, timeout, 5xx) escapava como exceção
  crua em vez de `SincronizacaoIncompleta`, quebrando o contrato documentado
  em todo o resto do módulo. Regressão:
  `test_erro_ao_buscar_discussoes_tambem_vira_sincronizacao_incompleta`.
- `_paginar` entrava em loop infinito se a API respondesse `has_more: true`
  sem `next_cursor` — a mesma página seria repedida para sempre, travando a
  Lambda até o timeout em vez de falhar com um diagnóstico. Confirmado
  reproduzindo o loop de verdade (com timeout de shell) antes de corrigir.
  Regressão: `test_has_more_sem_next_cursor_nao_entra_em_loop_infinito`.

## Próximo passo manual (usuária)

Antes de qualquer wiring em produção, falta cadastrar a integração do Notion:

1. Criar uma integração interna no Notion e compartilhar a página da coleção com ela.
2. Registrar o token e o `page_id` no SSM Parameter Store, num terminal separado (nunca colado na conversa):
   ```sh
   aws ssm put-parameter --profile perfil-padrao --region us-east-1 \
     --name /frase-diaria/notion-token --type SecureString --value 'SEU_TOKEN' --overwrite
   aws ssm put-parameter --profile perfil-padrao --region us-east-1 \
     --name /frase-diaria/notion-pagina-id --type String --value 'SEU_PAGE_ID' --overwrite
   ```

O wiring em `infraestrutura/composicao.py` (trocar `ColecaoFixture` por um adaptador real) só faz sentido depois que o ticket 11 (persistência/cache) e o ticket 12 (renderização) decidirem como `ColecaoValida` vira `Frase`.

## Verificação

O gate do repositório foi executado e passou:

- `ruff check` e `ruff format --check`
- `mypy` estrito
- `pytest`

Resultado local: 250 testes passaram, incluindo o cliente Notion (paginação completa, paginação incompleta nunca devolve resultado parcial, rate limit, acesso negado, sanitização do token) e o leitor (item preenchido vira frase, item vazio não, subpágina ignorada, conteúdo solto vira diagnóstico, lista numerada aninhada não cria frase independente, descendentes recursivos, discussões e acesso negado a elas, coleção totalmente vazia é legítima, erro em qualquer nível vira `SincronizacaoIncompleta`) — tudo com um cliente falso, sem rede real.
