"""Notion: busca blocos e converte o conteúdo em representação preservável.

`cliente.py` fala HTTP com a API (paginação, autenticação, erros sanitizados).
`leitura.py` decide o que é frase, o que é descendente e o que é ruído, e
produz a `ColecaoValida` do domínio (`dominio/colecao.py`). Persistência do
snapshot e cache de indisponibilidade são do ticket 11; renderização para o
Telegram é do ticket 12 — aqui o conteúdo só é preservado, não traduzido.
"""
