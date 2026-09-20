# site-doc

O site de documentação (produto + bastidores) do `frase-diaria-telegram`,
construído com [Docusaurus](https://docusaurus.io/).

## Instalação

```bash
npm install
```

## Desenvolvimento local

```bash
npm start
```

Abre um servidor local com recarregamento automático a cada mudança.

## Build

```bash
npm run build
```

Gera os arquivos estáticos em `build/`.

## Publicação

Não use `npm run deploy` (fluxo padrão do Docusaurus baseado na branch
`gh-pages`) — este projeto usa GitHub Pages com fonte **GitHub Actions**. A
publicação acontece automaticamente pelo workflow
`.github/workflows/site-doc.yml`, disparado por push em `main` quando algo em
`site-doc/` muda, ou manualmente via `workflow_dispatch`.

Site publicado: https://soamazyng.github.io/frase-diaria-telegram/
