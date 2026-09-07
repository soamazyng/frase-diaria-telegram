# 10 — Sincronização com Notion substitui as fixtures

**What to build:** `/frase` passa a entregar frases reais da coleção do Notion. A leitura percorre toda a paginação e os descendentes relevantes, ignora o que não é frase, e só publica um snapshot depois de concluir e validar a leitura inteira.

**Blocked by:** 05 — /frase entrega uma frase de fixture.

**Status:** em andamento em 2026-09-07 — núcleo de leitura e conversão pronto e
testado, ver `docs/10-sincronizacao-com-notion.md`. Falta o passo manual da
usuária (credencial de produção + `page_id` no SSM, fora do repositório) e a
decisão de wiring, que chega com os tickets 11 (persistência/cache) e 12
(renderização) — só então este ticket pode ser marcado concluído.

- [ ] A integração de produção tem acesso de leitura à página, com credencial cadastrada fora do repositório. — **pendente, passo manual da usuária.**
- [x] Apenas itens numerados preenchidos do nível da coleção viram frases; o conteúdo descendente pertence à frase que o contém e uma lista numerada interna não cria frases independentes.
- [x] Blocos de subpágina e o projeto inteiro são ignorados; itens vazios não viram frases (AC10).
- [x] A identidade estável da frase é o identificador do bloco raiz; mover ou editar mantém a identidade, apagar e recriar cria outra, e igualdade de texto nunca serve como deduplicação.
- [x] Conteúdo preservado em ordem, com rich text e vínculos associados; autoria misturada ao texto é conservada literalmente, sem heurística de separação.
- [x] Comentários pessoais no corpo entram na frase; discussões nativas do bloco são recuperadas quando o acesso permitir, e a limitação de acesso aparece no diagnóstico em vez de virar extração incompleta silenciosa.
- [x] Conteúdo solto de associação ambígua gera diagnóstico, sem atribuição inventada.
- [x] Toda a paginação e a leitura de filhos são percorridas antes de o snapshot ser publicado.
- [ ] Leitura paginada incompleta, erro de autorização ou timeout conservam o snapshot anterior e não geram exclusões (AC08). — **o sinal está pronto (`SincronizacaoIncompleta`); a conservação de fato depende da persistência do ticket 11.**
- [x] A quantidade de frases é descoberta a cada sincronização, sem número fixo no código.
