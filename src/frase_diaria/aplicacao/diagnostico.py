import re


def erro_sanitizado(erro: str | None) -> str:
    """Preserva somente categorias conhecidas; texto externo nunca é persistido."""
    if not erro:
        return ""
    if re.fullmatch(r"(?:Bot API respondeu )?HTTP [45][0-9]{2}", erro):
        return erro
    if erro in {
        "todas as frases reservadas",
        "coleção sem frases elegíveis",
        "frase reservada não está mais na coleção",
        "conflito de concorrência ao reservar frase",
        "lease do pedido pertence a outro executor",
        "outro executor já avançou este pedido",
    }:
        return erro
    return "erro de integração"
