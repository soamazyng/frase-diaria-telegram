# 02 — Esqueleto do projeto e /health local

**What to build:** um projeto Python que roda, testa e passa na análise estática na máquina da desenvolvedora, com `GET /health` respondendo saúde básica e identificador de versão. Nenhum comportamento de produto ainda — este ticket existe para tornar fáceis todas as mudanças seguintes.

**Blocked by:** None — can start immediately.

**Status:** concluído em 2026-09-06

- [x] Runtime Python suportado escolhido e fixado, com dependências travadas em versões testadas.
- [x] Módulos separados por responsabilidade: domínio, aplicação, Notion, Telegram, persistência, infraestrutura.
- [x] Relógio, gerador aleatório e integrações externas expostos como dependências substituíveis; os casos de uso não importam FastAPI nem formatos de evento AWS.
- [x] `GET /health` devolve saúde e identificador de versão, sem dados pessoais nem segredos.
- [x] Comando único roda a suíte de testes; comando único roda a análise estática; ambos passam num repositório limpo.
- [x] É possível rodar um único teste isoladamente, e o comando está documentado.
- [x] CLAUDE.md atualizado com os comandos reais de build, teste e análise.
