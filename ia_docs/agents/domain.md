# Domain Docs

Como as skills de engenharia devem consumir a documentação de domínio deste repositório
ao explorar o código.

## Antes de explorar, leia isto

- **`CONTEXT.md`** na raiz do repositório, ou
- **`CONTEXT-MAP.md`** na raiz, se existir: aponta para um `CONTEXT.md` por contexto. Ler
  cada um relevante ao tópico.
- **`ia_docs/adr/`**: ler ADRs que toquem a área em que você vai trabalhar.

Se algum desses arquivos não existir, **prossiga em silêncio**. Não sinalize a ausência;
não sugira criá-los de antemão. A skill `/domain-modeling` (acessada via
`/grill-with-docs` e `/improve-codebase-architecture`) os cria sob demanda quando termos
ou decisões forem de fato resolvidos.

## Estrutura de arquivos

Repositório single-context (é este):

```
/
├── CONTEXT.md
├── ia_docs/adr/
│   ├── 0001-....md
│   └── 0002-....md
└── src/
```

Nota de adaptação: os templates padrão desta skill referenciam `docs/adr/`. Neste
repositório, `docs/` foi renomeada para `ia_docs/` para reservar `docs/` a um site
Docusaurus publicado via GitHub Pages — logo, ADRs (quando existirem) vão em
`ia_docs/adr/`, não em `docs/adr/`.

## Use o vocabulário do glossário

Quando sua saída nomear um conceito de domínio (num título de issue, numa proposta de
refatoração, numa hipótese, num nome de teste), usar o termo como definido em
`CONTEXT.md`. Não derivar para sinônimos que o glossário evita explicitamente.

Se o conceito que você precisa ainda não estiver no glossário, isso é um sinal: ou você
está inventando vocabulário que o projeto não usa (reconsiderar), ou há uma lacuna real
(registrar para `/domain-modeling`).

## Sinalize conflitos de ADR

Se sua saída contradisser um ADR existente, torne isso explícito em vez de sobrescrever
silenciosamente:

> _Contradiz o ADR-0007 (nome da decisão), mas vale reabrir porque…_
