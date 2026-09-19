# Snapshot durável, cache e fallback do Notion

**Ticket:** 11 — Snapshot durável, cache e fallback do Notion

## Objetivo

Persistir o resultado da sincronização e continuar entregando frases quando o Notion está fora do ar, sem nunca ressuscitar itens excluídos nem reenviar uma frase que a fonte apagou no meio de uma entrega. Fechar a wiring de produção: o worker passa a ler frases reais do Notion, com cache, em vez da coleção embutida.

## O que foi construído

**Persistência do snapshot** (`persistencia/colecao.py`, `SnapshotPersistido` em `dominio/colecao.py`) — um único item guarda `identificador`, `instante`, `resultado` (`valida`/`vazia`), `quantidade` e as frases preservadas inteiras. Cabe em um item porque a coleção é pessoal e pequena (dezenas de frases) — o mesmo raciocínio já aplicado ao ciclo. `substituir` grava tudo de uma vez: uma frase que saiu da coleção não sobra depois de uma sincronização bem-sucedida que não a trouxe mais, e uma coleção legitimamente vazia vira um item com lista vazia. Não há histórico de versões — "referência ao snapshot ativo" simplificou para "o único snapshot existe é o ativo"; se isso deixar de bastar, a virada para itens por versão é o próximo passo.

**Sincronização com cache** (`aplicacao/sincronizar_colecao.py`, `SincronizarColecao`) — lê a fonte a cada chamada; numa leitura bem-sucedida (mesmo vazia), publica o novo snapshot e não usa cache; numa `SincronizacaoIncompleta`, cai para o último snapshot persistido, informando `usou_cache`, o instante desse snapshot e o erro da sincronização (AC09); sem nenhum snapshot para cair, a falha propaga (AC09, "sem cache registra falha").

**Wiring em produção** (`infraestrutura/composicao.py`, `infraestrutura/fonte_notion.py`) — `ColecaoFixture` foi removida (arquivo morto, sem mais nenhuma referência); o worker agora usa `FonteDeFrasesNotion`, que chama `SincronizarColecao` a cada `listar()` — ou seja, a cada tentativa que vá enviar conteúdo, exatamente como a spec pede. A conversão de `FrasePreservada` (conteúdo preservado, rich text) para `Frase` (pronta para envio) é um **placeholder deliberado**: concatena o texto literal dos trechos numa única parte, sem formatação nem divisão inteligente — isso é o ticket 12.

**AC07, sem mudança de código** — `Ciclo.elegiveis`/`esgotado`/`candidatas_a_primeira` já recebem `ativas: tuple[str,...]` fresco a cada consulta (ticket 06). Uma frase nova inserida já entra elegível; uma edição não toca a marca de consumo (o ciclo só conhece identidade); uma exclusão já some das elegíveis preservando o histórico de consumo. A verificação real contra a coleção do ticket 10 já exercitou isso.

**Frase reservada excluída, sem nada enviado** (`dominio/pedido.py::liberar_frase_excluida`, `aplicacao/processar_pedido.py::_escolher`) — se a frase reservada de um pedido some da fonte antes de qualquer parte confirmada, o ciclo libera a reserva antiga e uma nova seleção roda como se o pedido nunca tivesse reservado nada; a troca e a nova reserva acontecem na mesma transação. Se já houver alguma parte confirmada, o comportamento antigo se mantém (falha preservando a frase consumida) — trocar de frase no meio de uma entrega quebraria a invariante de que uma frase é uma entrega lógica única.

**Conteúdo atualizado sem reler nada extra** — como `_escolher` já chama `self.fonte.listar()` (que sincroniza) a cada `_processar`, uma tentativa que retoma um pedido sem nada enviado automaticamente enxerga o conteúdo mais recente da frase reservada, sem nenhum código adicional.

## Onde a política fica

- `src/frase_diaria/dominio/colecao.py` — `SnapshotPersistido`.
- `src/frase_diaria/persistencia/colecao.py` — persistência do snapshot ativo.
- `src/frase_diaria/aplicacao/sincronizar_colecao.py` — decide publicar ou usar cache.
- `src/frase_diaria/aplicacao/portas.py` — `FonteDaColecao`, `RepositorioDeColecao`.
- `src/frase_diaria/dominio/pedido.py` — `liberar_frase_excluida`.
- `src/frase_diaria/aplicacao/processar_pedido.py` — `_escolher`/`_processar` tratam a troca de frase.
- `src/frase_diaria/infraestrutura/fonte_notion.py` — adapta a sincronização à porta `FonteDeFrases`; conversão-placeholder para texto plano.
- `src/frase_diaria/infraestrutura/composicao.py` — wiring de produção.

## Achados do code-review corrigidos

O `/code-review` cobriu domínio, persistência, aplicação e infraestrutura e encontrou
quatro problemas, todos corrigidos antes do commit:

- **Corrigido — concorrência/alta:** ao trocar de frase excluída, `_processar` mutava a
  variável `pedido` para `frase_reservada=None` **antes** de tentar a transação. Se a
  transação fosse recusada por conflito de versão, o código persistia esse `pedido` já
  liberado — mas o ciclo persistido continuava com a frase antiga reservada, e nenhum
  pedido mais a referenciava para liberá-la depois. Isso travaria o ciclo para sempre
  (a mesma catástrofe que o docstring de `ReservaTransacional` já alertava, por um
  caminho novo). Corrigido separando `pedido` (o que está de fato persistido) de
  `pedido_para_reservar` (a tentativa em memória): no `except`, sempre se grava a partir
  do `pedido` original, intocado. Regressão:
  `test_conflito_ao_trocar_de_frase_nao_orfaniza_a_reserva_antiga_no_ciclo` (falha sem a
  correção, confirmado revertendo e restaurando).
- **Corrigido — corretude/média:** `RepositorioDeColecaoDynamo.substituir` não persistia
  `ColecaoValida.diagnosticos` — um acesso negado ou conteúdo solto virava invisível assim
  que o container da Lambda encerrasse, contrariando o próprio domínio ("precisam ficar
  visíveis"). Corrigido serializando e lendo os diagnósticos.
- **Corrigido — concorrência/média:** `substituir` gravava com `put_item` incondicional;
  duas sincronizações concorrentes terminando fora de ordem deixariam a mais antiga
  sobrescrever a mais nova, ressuscitando momentaneamente uma frase já excluída — o
  oposto do que "nunca ressuscita frases excluídas" promete. Corrigido com uma condição
  sobre `instante` (aceita instantes iguais, para não recusar uma nova gravação com o
  mesmo relógio parado, como em teste; só recusa uma gravação mais antiga que a já
  persistida).
- **Corrigido — robustez/média:** `_para_frase` (o placeholder de texto plano) podia
  gerar uma parte vazia se nenhum bloco de uma frase tivesse rich text (ex.: um bloco de
  imagem sozinho), e `Frase.__post_init__` rejeitaria isso — derrubando `listar()` **para
  a coleção inteira**, não só para aquela frase. Corrigido para ignorar (com log) só a
  frase problemática.

## Fora do escopo desta sessão

- **Renderização rica e divisão de mensagens** (ticket 12) — `FonteDeFrasesNotion` produz uma única parte de texto plano por frase; formatação, links, imagens e divisão inteligente ficam para lá.
- **`/status`** (ticket 15) — os dados de `usou_cache`, `instante_do_snapshot` e `erro_da_sincronização` já existem em `ResultadoDaSincronizacao`, mas nada os expõe pela HTTP ainda.

## Verificação

O gate do repositório foi executado e passou:

- `ruff check` e `ruff format --check`
- `mypy` estrito
- `pytest`

Resultado local: 275 testes passaram, incluindo persistência do snapshot (sobrevive a reinício, rich text/discussões/diagnósticos preservados, substituição completa, identificador novo a cada gravação, gravação mais antiga não sobrescreve a mais recente), a sincronização com cache (sucesso não usa cache, coleção vazia substitui o cache, indisponibilidade com e sem cache), o adaptador de conversão para texto plano (ignora frase sem conteúdo textual em vez de derrubar a listagem inteira), e o novo comportamento de troca de frase excluída em `ProcessarPedido` (incluindo a regressão do conflito de concorrência que orfanizaria a reserva) — todas confirmadas com o ciclo falha-sem-a-correção / passa-com-ela.
