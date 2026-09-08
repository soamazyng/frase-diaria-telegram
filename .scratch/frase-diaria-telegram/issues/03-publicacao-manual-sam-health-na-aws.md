# 03 — Publicação manual em SAM: /health vivo na AWS

**What to build:** a mesma aplicação do ticket 02 respondendo em uma URL pública da AWS, publicada por um comando manual. É o primeiro tracer bullet de infraestrutura: prova que empacotamento, entrada HTTP, permissões e persistência existem antes de haver produto para publicar.

**Blocked by:** 01 — Elegibilidade e estimativa de custo AWS/GitHub; 02 — Esqueleto do projeto e /health local.

**Status:** concluído em 2026-09-07 — procedimento em `docs/03-publicacao-manual.md`

- [x] SAM declara Lambda, HTTP API, tabela DynamoDB, grupo de logs e permissões IAM específicas por função.
- [x] Recursos duráveis de dados ficam em stack separada dos recursos de aplicação, com proteção contra exclusão e retenção configuradas.
- [x] Criptografia dos serviços habilitada; nenhum recurso exige VPC ou NAT.
- [x] Publicação por comando manual documentada, incluindo os parâmetros necessários.
- [x] `GET /health` público responde com o identificador da versão publicada.
- [x] Republicar a stack de aplicação não altera nem apaga a stack de dados.
- [x] Retenção dos logs técnicos configurada (proposta inicial de 14 dias).
